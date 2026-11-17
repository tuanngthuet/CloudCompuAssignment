"""queue HTTP API."""
from uuid import UUID
from fastapi import Request
from app import __version__
from app.models import LabSession
import app.modules.auth.service as auth
import app.modules.booking.service as svc
import app.infrastructure.redis.admission as booking_queue
from app.schemas import QueueInput
from fastapi import APIRouter
from app.shared.http import DB

router = APIRouter()

@router.get('/readyz/queue')
def queue_ready(db=DB):
    p = booking_queue.policy(db, shared_lock=True)
    if not p.enabled:
        return {'status': 'disabled', 'version': __version__}
    booking_queue.RedisQueue().call('ready', p)
    return {'status': 'ready', 'version': __version__}


def queue_operation(session_id, request, db, operation):
    user, _ = auth.authenticate(db, request, write=True)
    lab = db.get(LabSession, session_id)
    svc.require(lab is not None, 404, 'not_found', 'Không có ca')
    return booking_queue.action(db, user.id, lab, operation, svc.now(db))


@router.post('/lab-sessions/{session_id}/queue/join')
def join_queue(session_id: UUID, data: QueueInput, request: Request, db=DB):
    return queue_operation(session_id, request, db, 'join')


@router.post('/lab-sessions/{session_id}/queue/heartbeat')
def heartbeat_queue(session_id: UUID, data: QueueInput, request: Request, db=DB):
    return queue_operation(session_id, request, db, 'heartbeat')


@router.post('/lab-sessions/{session_id}/queue/leave')
def leave_queue(session_id: UUID, data: QueueInput, request: Request, db=DB):
    return queue_operation(session_id, request, db, 'leave')


