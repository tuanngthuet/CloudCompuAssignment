"""Bounded maintenance; dry-run is the default. No source/user reset operations."""

import argparse
from datetime import timedelta, datetime, timezone
import json
import uuid
from sqlalchemy import select, delete, tuple_
from sqlalchemy.dialects.postgresql import insert
from app.infrastructure.database.session import Session
from app.models import (
    MaintenanceState,
    User,
    LoginSession,
    AuthChallenge,
    RateLimit,
    IdempotencyRecord,
    OutboxEvent,
    NotificationDelivery,
    PlatformEvent,
    EmailJob,
    WebhookInbox,
    StorageObject,
    LabSession,
    CheckinPolicyEvent,
    AdminAudit,
    AuditEvent,
)
from app.modules.booking.service import now
from app.infrastructure.storage.objects import storage, LocalStorage
from app.infrastructure.storage.registry import is_referenced


def inventory(adapter):
    if isinstance(adapter, LocalStorage):

        def walk(root):
            # Sort a directory at a time; stop traversal when the batch is full.
            for path in sorted(
                root.iterdir(), key=lambda p: p.name + ("/" if p.is_dir() else "")
            ):
                if path.is_symlink():
                    continue
                if path.is_dir():
                    yield from walk(path)
                elif path.is_file():
                    yield (
                        str(path.relative_to(adapter.root)),
                        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
                    )

        for folder in ("events", "rooms", "users"):
            root = adapter.root / folder
            if root.exists():
                yield from walk(root)
    else:
        prefix = (adapter.prefix + "/") if adapter.prefix else ""
        for folder in ("events/", "rooms/", "users/"):
            for page in adapter.client.get_paginator("list_objects_v2").paginate(
                Bucket=adapter.bucket, Prefix=prefix + folder
            ):
                for item in page.get("Contents", []):
                    yield item["Key"][len(prefix) :], item["LastModified"]


def gc_objects(execute, limit=100, heartbeat=lambda: None):
    from app.models import MaintenanceState

    adapter = storage()
    found = []
    scanned = 0
    last = ""
    exhausted = True
    with Session() as db:
        state = db.get(MaintenanceState, "gc")
        cursor = state.cursor if state else ""

    for key, modified in inventory(adapter):
        if key <= cursor:
            continue
        scanned += 1
        last = key
        if modified <= datetime.now(timezone.utc) - timedelta(hours=24):
            with Session() as db:
                if is_referenced(db, key):
                    if scanned >= limit * 10:
                        exhausted = False
                        break
                    continue
            found.append(key)
            if execute:
                with Session.begin() as db:
                    db.execute(
                        insert(StorageObject)
                        .values(key=key, state="STAGED", created_at=modified)
                        .on_conflict_do_nothing()
                    )
                    row = db.get(StorageObject, key, with_for_update=True)
                    if row.state == "REFERENCED" and not is_referenced(db, key):
                        row.state = "STAGED"
        if scanned >= limit * 10 or len(found) >= limit:
            exhausted = False
            break
    if execute:
        with Session.begin() as db:
            db.execute(
                insert(MaintenanceState).values(key="gc").on_conflict_do_nothing()
            )
            state = db.get(MaintenanceState, "gc", with_for_update=True)
            state.cursor = "" if exhausted else last
    if not execute:
        return len(found)
    # Resume previously marked deletes even when the provider no longer lists them.
    with Session() as db:
        keys = list(
            db.scalars(
                select(StorageObject.key)
                .where(
                    StorageObject.state.in_(("STAGED", "QUARANTINED", "DELETING")),
                    StorageObject.failures < 10,
                )
                .order_by(StorageObject.created_at)
                .limit(limit)
            )
        )
    deleted = 0
    for key in keys:
        heartbeat()
        remove = False
        with Session.begin() as db:
            row = db.scalar(
                select(StorageObject)
                .where(StorageObject.key == key)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                continue
            if is_referenced(db, key):
                row.state = "REFERENCED"
                row.quarantine_at = None
                continue
            clock = now(db)
            if row.created_at > clock - timedelta(hours=24):
                continue
            if row.state == "DELETING":
                remove = True
            elif row.quarantine_at is None:
                row.quarantine_at = clock
                row.state = "QUARANTINED"
            elif clock - row.quarantine_at >= timedelta(hours=24):
                row.state = "DELETING"
                remove = True
        if remove:
            try:
                adapter.delete(key)
            except Exception:
                with Session.begin() as db:
                    row = db.get(StorageObject, key)
                    row.failures += 1
                from app.infrastructure.observability.metrics import emit

                emit("GarbageCollectionFailure")
                continue
            with Session.begin() as db:
                row = db.get(StorageObject, key)
                row.state = "DELETED"
                row.deleted_at = now(db)
            deleted += 1
    return deleted


def close_due(execute, limit):
    from app.modules.checkin.policy import deadline

    with Session.begin() as db:
        clock = now(db)
        due = list(
            db.scalars(
                select(LabSession)
                .where(
                    LabSession.checkin_enabled.is_(True),
                    (
                        (LabSession.checkin_close_mode == "end_at")
                        & (LabSession.end_at <= clock)
                    )
                    | (
                        (LabSession.checkin_close_mode == "custom")
                        & (LabSession.checkin_closes_at <= clock)
                    ),
                )
                .order_by(LabSession.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        if execute:
            for lab in due:
                lab.checkin_enabled = False
                lab.checkin_revision += 1
                db.add(
                    CheckinPolicyEvent(
                        session_id=lab.id,
                        actor_id=None,
                        enabled=False,
                        source="scheduled",
                        effective_at=deadline(lab),
                    )
                )
                db.add(PlatformEvent(kind="availability", subject_id=lab.id))
        return len(due)


def privacy(execute, limit):
    from app.models import Reservation
    from app.modules.notifications.jobs import enqueue
    from app.modules.accounts.service import revoke_sessions

    with Session() as db:
        clock = now(db)
        state = db.get(MaintenanceState, "privacy")
        cursor = uuid.UUID(state.cursor) if state and state.cursor else uuid.UUID(int=0)
        ids = list(
            db.scalars(
                select(User.id)
                .where(
                    User.id > cursor,
                    User.role == "student",
                    User.status == "ACTIVE",
                    User.last_activity_at <= clock - timedelta(days=335),
                )
                .order_by(User.id)
                .limit(limit)
            )
        )
    if execute:
        with Session.begin() as db:
            db.execute(
                insert(MaintenanceState).values(key="privacy").on_conflict_do_nothing()
            )
            db.get(MaintenanceState, "privacy", with_for_update=True).cursor = (
                str(ids[-1]) if len(ids) == limit else ""
            )
    notices = anonymizations = review = 0
    for uid in ids:
        with Session.begin() as db:
            user = db.scalar(
                select(User)
                .where(User.id == uid)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
            clock = now(db)
            if (
                not user
                or user.role != "student"
                or user.status != "ACTIVE"
                or user.last_activity_at > clock - timedelta(days=335)
            ):
                continue
            future = db.scalar(
                select(Reservation.id)
                .join(LabSession, LabSession.id == Reservation.session_id)
                .where(
                    Reservation.user_id == uid,
                    (
                        (LabSession.end_at > clock)
                        & Reservation.status.in_(("HELD", "CONFIRMED", "CHECKED_IN"))
                    )
                    | (
                        (Reservation.status == "HELD")
                        & (Reservation.hold_expires_at > clock)
                    ),
                )
                .limit(1)
            )
            if future:
                continue
            if user.anonymization_notice_at is None:
                if user.email_verified_at and user.email:
                    notices += 1
                    if execute:
                        user.anonymization_notice_at = clock
                        enqueue(
                            db,
                            user.id,
                            "anonymization",
                            user.email,
                            context={"notice_at": clock.isoformat()},
                        )
                else:
                    review += 1
            elif user.last_activity_at <= clock - timedelta(days=365):
                if (
                    user.anonymization_notice_delivered_at
                    and user.anonymization_notice_delivered_at
                    <= clock - timedelta(days=30)
                ):
                    anonymizations += 1
                    if execute:
                        revoke_sessions(db, uid)
                        user.username = "anon_" + user.id.hex
                        user.password_hash = "!anonymized"
                        user.status = "ANONYMIZED"
                        user.full_name = user.cccd = user.phone = user.email = ""
                        user.pending_email = None
                        user.email_verified_at = None
                        user.avatar_key = None
                elif user.anonymization_notice_at <= clock - timedelta(days=30):
                    review += 1
    return {
        "notices": notices,
        "anonymizations": anonymizations,
        "privacy_review": review,
    }


def prune(execute, limit):
    summary = {}
    with Session.begin() as db:
        clock = now(db)
        cleanup = [
            (LoginSession, LoginSession.expires_at < clock - timedelta(days=7)),
            (AuthChallenge, AuthChallenge.expires_at < clock - timedelta(days=7)),
            (RateLimit, RateLimit.window_at < clock - timedelta(days=1)),
            (
                IdempotencyRecord,
                IdempotencyRecord.created_at < clock - timedelta(days=30),
            ),
            (
                WebhookInbox,
                (WebhookInbox.processed_at.is_not(None))
                & (WebhookInbox.created_at < clock - timedelta(days=90)),
            ),
            (
                OutboxEvent,
                (OutboxEvent.published_at.is_not(None))
                & (OutboxEvent.created_at < clock - timedelta(days=90)),
            ),
            (
                PlatformEvent,
                (PlatformEvent.published_at.is_not(None))
                & (PlatformEvent.created_at < clock - timedelta(days=90)),
            ),
            (
                NotificationDelivery,
                (NotificationDelivery.status.in_(("SENT", "SKIPPED")))
                & (NotificationDelivery.completed_at < clock - timedelta(days=365)),
            ),
            (AuditEvent, AuditEvent.created_at < clock - timedelta(days=365)),
            (AdminAudit, AdminAudit.created_at < clock - timedelta(days=365)),
            (
                CheckinPolicyEvent,
                CheckinPolicyEvent.created_at < clock - timedelta(days=365),
            ),
            (
                StorageObject,
                (StorageObject.state == "DELETED")
                & (StorageObject.deleted_at < clock - timedelta(days=90)),
            ),
        ]
        for model, condition in cleanup:
            keys = list(
                db.execute(
                    select(*model.__table__.primary_key.columns)
                    .where(condition)
                    .limit(limit)
                )
            )
            summary[model.__tablename__] = len(keys)
            if execute and keys:
                columns = list(model.__table__.primary_key.columns)
                match = (
                    columns[0].in_([k[0] for k in keys])
                    if len(columns) == 1
                    else tuple_(*columns).in_([tuple(k) for k in keys])
                )
                db.execute(
                    delete(model)
                    .where(condition, match)
                    .execution_options(synchronize_session=False)
                )
        jobs = list(
            db.scalars(
                select(EmailJob)
                .where(
                    EmailJob.created_at < clock - timedelta(days=90),
                    (EmailJob.recipient != "") | (EmailJob.context != {}),
                    EmailJob.status.in_(
                        (
                            "ACCEPTED",
                            "DELIVERED",
                            "SKIPPED",
                            "HARD_BOUNCE",
                            "BLOCKED",
                            "COMPLAINT",
                            "FAILED",
                        )
                    ),
                )
                .limit(limit)
            )
        )
        summary["email_contexts"] = len(jobs)
        if execute:
            for job in jobs:
                job.context = {}
                job.recipient = ""
    return summary


def run(execute=False, limit=100):
    from app.models import MaintenanceState

    owner = uuid.uuid4()
    if execute:
        with Session.begin() as db:
            db.execute(
                insert(MaintenanceState)
                .values(key="maintenance")
                .on_conflict_do_nothing()
            )
            lease = db.scalar(
                select(MaintenanceState)
                .where(MaintenanceState.key == "maintenance")
                .with_for_update()
            )
            clock = now(db)
            if lease.lease_until and lease.lease_until > clock:
                return {"status": "already_running"}
            lease.lease_until = clock + timedelta(minutes=15)
            lease.lease_owner = owner

    def renew():
        if not execute:
            return
        with Session.begin() as db:
            lease = db.get(MaintenanceState, "maintenance", with_for_update=True)
            clock = now(db)
            if not lease or lease.lease_owner != owner or lease.lease_until <= clock:
                raise RuntimeError("Maintenance lease expired")
            lease.lease_until = clock + timedelta(minutes=15)

    try:
        summary = {"dry_run": not execute, "checkins_due": close_due(execute, limit)}
        renew()
        summary.update(privacy(execute, limit))
        if execute:
            from app.modules.admin.lifecycle import cancel_batch

            # Cancel a bounded batch using the normal global lock order.
            with Session.begin() as db:
                summary["cancellations"] = cancel_batch(db, limit)
            from app.modules.notifications.jobs import process_webhooks

            with Session.begin() as db:
                process_webhooks(db)
        renew()
        summary.update(prune(execute, limit))
        summary["objects"] = gc_objects(execute, limit, heartbeat=renew)
        return summary
    finally:
        if execute:
            with Session.begin() as db:
                lease = db.get(MaintenanceState, "maintenance", with_for_update=True)
                if lease and lease.lease_owner == owner:
                    lease.lease_until = None
                    lease.lease_owner = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("limit1..1000")
    from app.infrastructure.observability.metrics import emit

    try:
        result = run(args.execute, args.limit)
    except Exception:
        emit("MaintenanceFailure")
        raise SystemExit(
            "Maintenance failed; inspect dependency health and scoped permissions."
        ) from None
    if args.execute:
        emit("MaintenanceSuccess")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
