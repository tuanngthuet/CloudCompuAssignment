from uuid import UUID
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from app.shared.http import DB
from app.models import Event, StaffAssignment, LabSession, Reservation, User
from app.schemas import CheckInInput
from app.modules.auth import service as auth
from app.modules.booking import service as svc
from app.modules.accounts.service import audit
from app.modules.sessions.service import lab_dict
from app.modules.tickets.service import ticket
from app.infrastructure.storage.objects import storage
from .service import find_ticket, inspection
from .policy import scope

router = APIRouter()


def staff_actor(db, request, write=False):
    actor, _ = auth.authenticate(db, request, write=write)
    svc.require(actor.role == "staff", 403, "forbidden", "Chỉ staff được phép.")
    return actor


def scoped(db, actor, reservation):
    lab = db.get(LabSession, reservation.session_id)
    scope(db, actor, lab)
    return lab


@router.get("/staff/lab-sessions")
def assigned(request: Request, db=DB):
    actor = staff_actor(db, request)
    return {
        "items": [
            lab_dict(row, db)
            | {"name": db.get(Event, row.event_id).name if row.event_id else "Ca"}
            for row in db.scalars(
                select(LabSession)
                .join(StaffAssignment, StaffAssignment.session_id == LabSession.id)
                .where(StaffAssignment.user_id == actor.id)
                .order_by(LabSession.start_at)
            )
        ]
    }


@router.post("/staff/check-ins/lookup")
def lookup(data: CheckInInput, request: Request, db=DB):
    actor = staff_actor(db, request, True)
    r = find_ticket(db, data.ticket_code)
    scoped(db, actor, r)
    output = inspection(db, r)
    profile = output["profile"]
    profile["cccd"] = ("••••••••" + profile["cccd"][-4:]) if profile["cccd"] else ""
    profile["email"] = ""
    profile["phone"] = ""
    profile["avatar_url"] = (
        f"/staff/check-ins/{r.id}/avatar" if profile["avatar_url"] else None
    )
    return output


@router.post("/staff/check-ins")
def checkin(data: CheckInInput, request: Request, db=DB):
    actor = staff_actor(db, request, True)
    r = find_ticket(db, data.ticket_code)
    scoped(db, actor, r)
    svc.require(bool(r.ticket_code), 409, "ticket_not_eligible", "Vé chưa xác nhận.")
    return ticket(
        svc.transition(db, actor.id, action="check-in", ticket_code=r.ticket_code)
    )


@router.post("/staff/check-ins/{reservation_id}/identity")
def reveal(reservation_id: UUID, request: Request, db=DB):
    actor = staff_actor(db, request, True)
    r = db.get(Reservation, reservation_id)
    svc.require(r is not None, 404, "not_found", "Không có vé.")
    scoped(db, actor, r)
    audit(db, actor.id, "checkin_identity_view", r.id)
    user = db.get(User, r.user_id)
    return {"full_name": user.full_name, "cccd": user.cccd}


@router.get("/staff/check-ins/{reservation_id}/avatar")
def avatar(reservation_id: UUID, request: Request, db=DB):
    actor = staff_actor(db, request)
    r = db.get(Reservation, reservation_id)
    svc.require(r is not None, 404, "not_found", "Không có vé.")
    scoped(db, actor, r)
    user = db.get(User, r.user_id)
    svc.require(bool(user.avatar_key), 404, "not_found", "Chưa có avatar.")
    try:
        data = storage().get(user.avatar_key)
    except Exception:
        raise svc.Problem(503, "storage_unavailable", "Chưa đọc được avatar.") from None
    return Response(data, media_type="image/jpeg")
