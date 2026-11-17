from uuid import UUID
from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import select, delete
from app.schemas import Input
from app.models import Event, LabSession, Reservation, SessionSeat, User
from app.shared.http import DB, admin
from app.modules.booking.service import require, now
from app.modules.accounts.service import audit
from app.modules.notifications.jobs import enqueue
from app.models import PlatformEvent, EmailJob
from app.modules.admin.service import event_dict

router = APIRouter()


class Reason(Input):
    reason: str = Field(min_length=1, max_length=500)


def lock_event(db, event_id):
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(event is not None, 404, "not_found", "Không có ca.")
    labs = list(
        db.scalars(
            select(LabSession)
            .where(LabSession.event_id == event_id)
            .order_by(LabSession.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    return event, labs


@router.get("/admin/events")
def all_events(request: Request, db=DB):
    from app.modules.auth.service import authenticate

    authenticate(db, request, admin=True)
    return [
        event_dict(event, db)
        for event in db.scalars(select(Event).order_by(Event.name))
    ]


@router.delete("/admin/events/{event_id}")
def delete_event(event_id: UUID, request: Request, db=DB):
    actor = admin(db, request)
    actor = db.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(
        actor.status == "ACTIVE" and actor.role == "admin",
        403,
        "forbidden",
        "Không có quyền quản trị.",
    )
    event, labs = lock_event(db, event_id)
    ids = [lab.id for lab in labs]
    require(
        not ids
        or db.scalar(
            select(Reservation.id).where(Reservation.session_id.in_(ids)).limit(1)
        )
        is None,
        409,
        "event_has_history",
        "Ca có lịch sử. Hãy hủy hoặc lưu trữ.",
    )
    for lab in labs:
        db.execute(delete(SessionSeat).where(SessionSeat.session_id == lab.id))
        db.delete(lab)
    audit(db, actor.id, "event_delete", event.id)
    db.flush()
    db.delete(event)
    return {"status": "deleted"}


@router.post("/admin/events/{event_id}/cancel", status_code=202)
def cancel_event(event_id: UUID, data: Reason, request: Request, db=DB):
    actor = admin(db, request)
    actor = db.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(
        actor.status == "ACTIVE" and actor.role == "admin",
        403,
        "forbidden",
        "Không có quyền quản trị.",
    )
    event, labs = lock_event(db, event_id)
    require(event.status != "ARCHIVED", 409, "session_inactive", "Ca đã lưu trữ.")
    if event.status != "CANCELLED":
        event.status = "CANCELLED"
        event.lifecycle_reason = data.reason
        event.lifecycle_at = now(db)
        event.lifecycle_actor = actor.id
        event.cancelled_at = now(db)
        event.cancelled_by = actor.id
        event.cancellation_reason = data.reason
        for lab in labs:
            lab.checkin_enabled = False
            lab.checkin_revision += 1
            db.add(PlatformEvent(kind="availability", subject_id=lab.id))
        audit(db, actor.id, "event_cancel", event.id, reason=data.reason)
    return {"status": "cancelled", "cleanup_pending": True}


@router.post("/admin/events/{event_id}/archive")
def archive(event_id: UUID, data: Reason, request: Request, db=DB):
    actor = admin(db, request)
    actor = db.scalar(
        select(User)
        .where(User.id == actor.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(
        actor.status == "ACTIVE" and actor.role == "admin",
        403,
        "forbidden",
        "Không có quyền quản trị.",
    )
    event, labs = lock_event(db, event_id)
    require(
        not labs
        or all(now(db) >= lab.end_at for lab in labs)
        or event.status == "CANCELLED",
        409,
        "event_not_finished",
        "Chỉ lưu trữ ca đã kết thúc hoặc đã hủy.",
    )
    if event.status != "ARCHIVED":
        event.status = "ARCHIVED"
        event.lifecycle_reason = data.reason
        event.lifecycle_at = now(db)
        event.lifecycle_actor = actor.id
        for lab in labs:
            lab.checkin_enabled = False
            lab.checkin_revision += 1
            db.add(PlatformEvent(kind="availability", subject_id=lab.id))
        audit(db, actor.id, "event_archive", event.id, reason=data.reason)
    return {"status": "archived"}


def cancel_batch(db, limit=100):
    # Lock users before schedules, as in booking. No Event UPDATE lock here.
    rows = list(
        db.scalars(
            select(Reservation.id)
            .join(LabSession, LabSession.id == Reservation.session_id)
            .join(Event, Event.id == LabSession.event_id)
            .where(
                Event.cancelled_at.is_not(None),
                ~select(EmailJob.id)
                .where(
                    EmailJob.reservation_id == Reservation.id,
                    EmailJob.kind == "cancelled",
                )
                .exists(),
                Reservation.status.in_(("HELD", "CONFIRMED", "CHECKED_IN")),
            )
            .order_by(Reservation.id)
            .limit(limit)
        )
    )
    # One global order for every lock held by this bounded batch.
    registrations = list(
        db.scalars(select(Reservation).where(Reservation.id.in_(rows)))
    )
    labs_by_id = {r.session_id: db.get(LabSession, r.session_id) for r in registrations}
    events = {lab.event_id: db.get(Event, lab.event_id) for lab in labs_by_id.values()}
    users = {r.user_id for r in registrations} | {
        e.cancelled_by for e in events.values() if e.cancelled_by
    }
    list(
        db.scalars(
            select(User)
            .where(User.id.in_(users))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    list(
        db.scalars(
            select(LabSession)
            .where(LabSession.id.in_(labs_by_id))
            .order_by(LabSession.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    from sqlalchemy import tuple_

    affected = {(r.session_id, r.seat_id) for r in registrations}
    if affected:
        list(
            db.scalars(
                select(SessionSeat)
                .where(
                    tuple_(SessionSeat.session_id, SessionSeat.seat_id).in_(affected)
                )
                .order_by(SessionSeat.session_id, SessionSeat.seat_id)
                .with_for_update()
            )
        )
    for rid in rows:
        r = db.get(Reservation, rid)
        lab = db.get(LabSession, r.session_id)
        event = db.get(Event, lab.event_id)
        marker = __import__("uuid").uuid5(
            __import__("uuid").NAMESPACE_URL, "labseat:cancel:" + str(rid)
        )
        from app.models import AuditEvent

        if db.get(EmailJob, marker):
            continue
        db.refresh(r)
        if r.status in ("HELD", "CONFIRMED"):
            r.status = "CANCELLED"
            db.add(
                AuditEvent(
                    actor_id=event.cancelled_by, reservation_id=r.id, action="CANCELLED"
                )
            )
        user = db.get(User, r.user_id)
        enqueue(
            db,
            user.id,
            "cancelled",
            user.email if user.email_verified_at else "",
            r.id,
            {"name": event.name, "reason": event.cancellation_reason},
            job_id=marker,
        )
        db.add(PlatformEvent(kind="availability", subject_id=lab.id))
    return len(rows)
