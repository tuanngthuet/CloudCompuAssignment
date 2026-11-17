"""booking HTTP API."""
from uuid import UUID
from fastapi import Request, Header
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from app.schemas import HoldInput
from fastapi import APIRouter
from app.shared.http import DB
from app.modules.tickets.service import ticket

from .idempotency import execute

router = APIRouter()

@router.post('/holds')
def hold(data: HoldInput, request: Request, db=DB, idempotency_key: str | None=Header(default=None, alias='Idempotency-Key', description='8-128 ASCII letters, digits or ._:-; same key replays the committed response')):
    user, _ = auth.authenticate(db,request,write=True)
    def mutate():
        r, clock = svc.hold(db,user.id,data.session_id,data.seat_id)
        return {'hold_id':r.id,'expires_at':r.hold_expires_at,'server_time':clock}
    return execute(db, user.id, idempotency_key, 'hold',
                   data.model_dump(mode='json'), mutate)


@router.post('/holds/{hold_id}/confirm')
def confirm(hold_id: UUID, request: Request, db=DB, idempotency_key: str | None=Header(default=None, alias='Idempotency-Key', description='8-128 ASCII letters, digits or ._:-; same key replays the committed response')):
    user, _ = auth.authenticate(db,request,write=True)
    return execute(db, user.id, idempotency_key, 'confirm',
                   {'hold_id': str(hold_id)}, lambda: ticket(svc.transition(db,user.id,hold_id,'confirm')))


@router.post('/reservations/{reservation_id}/cancel')
def cancel(reservation_id: UUID, request: Request, db=DB, idempotency_key: str | None=Header(default=None, alias='Idempotency-Key', description='8-128 ASCII letters, digits or ._:-; same key replays the committed response')):
    user, _ = auth.authenticate(db,request,write=True)
    return execute(db, user.id, idempotency_key, 'cancel',
                   {'reservation_id': str(reservation_id)}, lambda: ticket(svc.transition(db,user.id,reservation_id,'cancel')))


