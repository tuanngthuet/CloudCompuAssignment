from .policy import effective

"""Admin-only ticket inspection and explicit check-in policy; callers own transactions."""
from uuid import UUID
from sqlalchemy import select, or_
import app.modules.booking.service as svc
from app.models import (
    Reservation,
    LabSession,
    User,
    Event,
    Room,
    Seat,
    CheckinPolicyEvent,
)
from app.modules.tickets.service import ticket


def find_ticket(db, code):
    conditions = [Reservation.ticket_code == code]
    try:
        conditions.append(Reservation.id == UUID(code))
    except ValueError:
        pass
    row = db.scalar(select(Reservation).where(or_(*conditions)))
    svc.require(
        row is not None,
        404,
        "ticket_not_found",
        "Không tìm thấy vé. Kiểm tra lại mã hoặc QR.",
    )
    return row


def inspection(db, reservation):
    lab = db.get(LabSession, reservation.session_id)
    owner = db.get(User, reservation.user_id)
    event = db.get(Event, lab.event_id) if lab.event_id else None
    room = db.get(Room, lab.room_id)
    seat = db.get(Seat, reservation.seat_id)
    result = ticket(reservation)
    if reservation.status == "HELD" and reservation.hold_expires_at <= svc.now(db):
        result["status"] = "EXPIRED"
    status = result["status"]
    if status == "CHECKED_IN":
        reason = "Vé đã được check-in."
    elif status != "CONFIRMED":
        reason = {
            "HELD": "Vé chưa được xác nhận.",
            "CANCELLED": "Vé đã bị huỷ.",
            "EXPIRED": "Lượt giữ đã hết hạn.",
        }.get(status, "Vé không đủ điều kiện check-in.")
    elif not effective(db, lab):
        reason = "Ca chưa mở check-in. Mở check-in trong Quản lí ca để tiếp nhận vé."
    else:
        reason = "Vé hợp lệ. Có thể xác nhận check-in."
    return {
        "ticket": result,
        "session": {
            "id": lab.id,
            "name": event.name if event else room.name,
            "room_name": room.name,
            "seat_code": seat.seat_code,
            "start_at": lab.start_at,
            "end_at": lab.end_at,
            "checkin_enabled": effective(db, lab),
        },
        "profile": {
            "username": owner.username,
            "full_name": owner.full_name,
            "cccd": owner.cccd,
            "phone": owner.phone,
            "email": owner.email,
            "avatar_url": f"/admin/check-ins/{reservation.id}/avatar"
            if owner.avatar_key
            else None,
        },
        "can_check_in": status == "CONFIRMED" and effective(db, lab),
        "reason": reason,
    }


def change_policy(db, actor_id, session_id, enabled, close_mode=None, closes_at=None):
    # Same User -> LabSession ordering as booking/check-in. The exclusive lab
    # lock serializes this switch against the booking engine's SHARE lock.
    actor = db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    svc.require(
        actor is not None and actor.status == "ACTIVE" and actor.role == "admin",
        403,
        "forbidden",
        "Không có quyền quản trị.",
    )
    lab = db.scalar(
        select(LabSession)
        .where(LabSession.id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    svc.require(lab is not None, 404, "not_found", "Không có ca")
    from .policy import deadline, effective

    mode = close_mode or lab.checkin_close_mode
    svc.require(
        mode in ("end_at", "custom", "manual"),
        422,
        "invalid_input",
        "Chế độ đóng không hợp lệ.",
    )
    until = (
        closes_at
        if close_mode == "custom" or closes_at is not None
        else lab.checkin_closes_at
    )
    if mode != "custom":
        until = None
    svc.require(
        mode != "custom" or until is not None,
        422,
        "invalid_input",
        "Nhập hạn đóng check-in.",
    )
    target_deadline = (
        lab.end_at if mode == "end_at" else until if mode == "custom" else None
    )
    svc.require(
        not enabled or target_deadline is None or target_deadline > svc.now(db),
        409,
        "invalid_close_at",
        "Chọn hạn tương lai hoặc đóng thủ công.",
    )
    from app.models import Event

    parent = db.get(Event, lab.event_id) if lab.event_id else None
    svc.require(
        not enabled or parent is None or parent.status == "ACTIVE",
        409,
        "session_inactive",
        "Ca đã hủy hoặc lưu trữ.",
    )
    if (lab.checkin_enabled, lab.checkin_close_mode, lab.checkin_closes_at) != (
        enabled,
        mode,
        until,
    ):
        lab.checkin_enabled = enabled
        lab.checkin_close_mode = mode
        lab.checkin_closes_at = until
        lab.checkin_revision += 1
        db.add(
            CheckinPolicyEvent(session_id=lab.id, actor_id=actor_id, enabled=enabled)
        )
        from app.models import PlatformEvent
        from app.modules.accounts.service import audit

        db.add(PlatformEvent(kind="availability", subject_id=lab.id))
        audit(
            db,
            actor_id,
            "checkin_policy",
            lab.id,
            enabled=enabled,
            mode=mode,
            closes_at=target_deadline.isoformat() if target_deadline else None,
        )
    return {
        "session_id": lab.id,
        "checkin_enabled": effective(db, lab),
        "close_mode": mode,
        "closes_at": deadline(lab),
    }
