"""At-least-once publication and serialized, best-effort email deduplication."""

import json
from datetime import timedelta
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from app.infrastructure.database.session import Session
from app.models import OutboxEvent, NotificationDelivery, Reservation, User
from app.infrastructure.observability.metrics import emit

EVENT = "ReservationConfirmed"


def publish_batch(
    queue, batch_size=10, session_factory=Session, stopping=lambda: False
):
    if not 1 <= batch_size <= 100:
        raise ValueError("Batch size must be 1..100")
    sent = 0
    for _ in range(batch_size):
        if stopping():
            break
        # Per-row transaction bounds lock time. Other publishers skip this row.
        with session_factory.begin() as db:
            event = db.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.available_at <= func.clock_timestamp(),
                )
                .order_by(OutboxEvent.available_at, OutboxEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                break
            event.attempts += 1
            try:
                queue.publish(
                    json.dumps(
                        {
                            "event_id": str(event.id),
                            "event_type": event.event_type,
                            "reservation_id": str(event.reservation_id),
                        }
                    )
                )
            except Exception:
                # Ambiguous send results are retried: a duplicate is possible, loss is not.
                event.available_at = db.scalar(
                    select(func.clock_timestamp())
                ) + timedelta(seconds=min(300, 2 ** min(event.attempts, 8)))
                emit("OutboxPublishFailure")
            else:
                event.published_at = db.scalar(select(func.clock_timestamp()))
                emit("OutboxPublished")
                sent += 1
    with session_factory() as db:
        pending = db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
        )
        emit("OutboxPending", pending)
    return sent


def consume(body, email, session_factory=Session):
    payload = json.loads(body)
    from .jobs import dispatch, enqueue
    import uuid
    from app.models import EmailJob

    if (
        isinstance(payload, dict)
        and set(payload) == {"type", "job_id"}
        and payload["type"] == "email_job"
    ):
        return dispatch(UUID(payload["job_id"]), email, session_factory)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"event_id", "event_type", "reservation_id"}
        or payload["event_type"] != EVENT
    ):
        raise ValueError("Invalid event envelope")
    event_id, reservation_id = (
        UUID(payload["event_id"]),
        UUID(payload["reservation_id"]),
    )
    job_id = uuid.uuid5(uuid.NAMESPACE_URL, "labseat:confirmed:" + str(reservation_id))
    with session_factory.begin() as db:
        event = db.get(OutboxEvent, event_id)
        if (
            event is None
            or event.reservation_id != reservation_id
            or event.event_type != EVENT
        ):
            raise ValueError("Event not found")
        db.execute(
            insert(NotificationDelivery)
            .values(reservation_id=reservation_id, notification_type=EVENT)
            .on_conflict_do_nothing()
        )
        delivery = db.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.reservation_id == reservation_id,
                NotificationDelivery.notification_type == EVENT,
            )
            .with_for_update()
        )
        if delivery.status in ("SENT", "SKIPPED"):
            emit("EmailDuplicateSuppressed")
            return
        reservation = db.get(Reservation, reservation_id)
        user = db.get(User, reservation.user_id)
        if db.get(EmailJob, job_id) is None:
            enqueue(db, user.id, "ticket", user.email, reservation_id, job_id=job_id)
    dispatch(job_id, email, session_factory)
    with session_factory.begin() as db:
        job = db.get(EmailJob, job_id)
        delivery = db.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.reservation_id == reservation_id,
                NotificationDelivery.notification_type == EVENT,
            )
            .with_for_update()
        )
        if job.status in ("ACCEPTED", "DELIVERED", "DEFERRED", "SOFT_BOUNCE"):
            delivery.status = "SENT"
            delivery.provider_message_id = job.provider_message_id
        elif job.status in (
            "SKIPPED",
            "UNKNOWN",
            "HARD_BOUNCE",
            "COMPLAINT",
            "BLOCKED",
        ):
            delivery.status = "SKIPPED"
        else:
            raise RuntimeError("Email job is not complete")
        delivery.completed_at = func.clock_timestamp()
