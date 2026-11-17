"""admin HTTP API."""
from uuid import UUID
from fastapi import Request, Response, UploadFile, File, Form
from sqlalchemy import select
from app.models import Event
import app.modules.booking.service as svc
from app.infrastructure.storage.objects import storage
from fastapi import APIRouter
from app.shared.http import DB, admin
from app.modules.admin.service import event_dict, persist_ca

router = APIRouter()

@router.get('/events')
def list_events(db=DB):
    return [event_dict(event,db) for event in db.scalars(select(Event).where(Event.session_type.is_not(None), Event.poster_key.is_not(None), Event.status=='ACTIVE').order_by(Event.name))]


@router.post('/admin/events', status_code=201)
def create_event(request: Request, data: str=Form(...), poster: UploadFile | None=File(None), db=DB):
    return persist_ca(db,request,data,poster)


@router.patch('/admin/events/{event_id}')
def update_event(event_id: UUID, request: Request, data: str=Form(...), poster: UploadFile | None=File(None), db=DB):
    admin(db,request)
    event=db.scalar(select(Event).where(Event.id==event_id).with_for_update())
    svc.require(event is not None,404,'not_found','Không có ca')
    return persist_ca(db,request,data,poster,event)


@router.get('/events/{event_id}/images/{slot}')
def read_event_image(event_id: UUID, slot: str, db=DB):
    svc.require(slot == 'poster', 404, 'not_found', 'Không có ảnh')
    event = db.get(Event, event_id)
    key = getattr(event, slot + '_key') if event else None
    svc.require(key is not None, 404, 'not_found', 'Không có ảnh')
    try:
        data = storage().get(key)
    except Exception:
        raise svc.Problem(503, 'storage_unavailable', 'Không thể đọc ảnh') from None
    return Response(data, media_type='image/jpeg')


