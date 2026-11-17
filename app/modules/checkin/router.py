"""Admin-only lookup, profile inspection and explicit check-in confirmation."""

from uuid import UUID
from fastapi import Request, Response, APIRouter
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from app.schemas import CheckInInput, CheckinPolicyInput
from app.shared.http import DB
from app.models import Reservation, User
from app.infrastructure.storage.objects import storage
from app.modules.tickets.service import ticket
from .service import find_ticket, inspection, change_policy

router = APIRouter()


@router.post("/admin/check-ins/lookup")
def lookup(data: CheckInInput, request: Request, db=DB):
    auth.authenticate(db, request, write=True, admin=True)
    return inspection(db, find_ticket(db, data.ticket_code))


@router.patch("/admin/lab-sessions/{session_id}/check-in")
def set_checkin_policy(
    session_id: UUID, data: CheckinPolicyInput, request: Request, db=DB
):
    actor, _ = auth.authenticate(db, request, write=True, admin=True)
    return change_policy(
        db, actor.id, session_id, data.enabled, data.close_mode, data.closes_at
    )


@router.get("/admin/check-ins/{reservation_id}/avatar")
def registrant_avatar(reservation_id: UUID, request: Request, db=DB):
    auth.authenticate(db, request, admin=True)
    reservation = db.get(Reservation, reservation_id)
    svc.require(reservation is not None, 404, "not_found", "Không có vé")
    owner = db.get(User, reservation.user_id)
    svc.require(bool(owner.avatar_key), 404, "not_found", "Chưa có ảnh đại diện")
    try:
        content = storage().get(owner.avatar_key)
    except Exception:
        raise svc.Problem(
            503, "storage_unavailable", "Chưa tải được ảnh đại diện."
        ) from None
    return Response(content, media_type="image/jpeg")


@router.post("/admin/check-ins")
def check_in(data: CheckInInput, request: Request, db=DB):
    actor, _ = auth.authenticate(db, request, write=True, admin=True)
    reservation = find_ticket(db, data.ticket_code)
    svc.require(
        bool(reservation.ticket_code),
        409,
        "ticket_not_eligible",
        "Vé chưa được xác nhận",
    )
    return ticket(
        svc.transition(
            db, actor.id, action="check-in", ticket_code=reservation.ticket_code
        )
    )
