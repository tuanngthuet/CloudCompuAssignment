from sqlalchemy import select
from app.models import Event, StaffAssignment
from app.modules.booking.service import require, now


def deadline(lab):
    return (
        lab.end_at
        if lab.checkin_close_mode == "end_at"
        else lab.checkin_closes_at
        if lab.checkin_close_mode == "custom"
        else None
    )


def effective(db, lab):
    event = db.get(Event, lab.event_id) if lab.event_id else None
    until = deadline(lab)
    return bool(
        lab.checkin_enabled
        and (until is None or now(db) < until)
        and (event is None or event.status == "ACTIVE")
    )


def scope(db, actor, lab, lock=False):
    require(
        actor.status == "ACTIVE" and actor.role in ("admin", "staff"),
        403,
        "forbidden",
        "Không có quyền check-in.",
    )
    if actor.role == "staff":
        require(
            actor.email_verified_at is not None,
            403,
            "email_verification_required",
            "Staff cần xác minh email.",
        )
        query = select(StaffAssignment).where(
            StaffAssignment.session_id == lab.id, StaffAssignment.user_id == actor.id
        )
        if lock:
            query = query.with_for_update(read=True)
        require(
            db.scalar(query) is not None,
            404,
            "not_found",
            "Không có ca được phân công.",
        )
        event = db.get(Event, lab.event_id) if lab.event_id else None
        require(
            event is None or event.status != "ARCHIVED",
            404,
            "not_found",
            "Ca đã lưu trữ.",
        )
