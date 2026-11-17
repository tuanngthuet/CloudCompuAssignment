"""sessions HTTP API."""
from uuid import UUID
from fastapi import Request
from sqlalchemy import select, or_, and_, func
from app.models import Seat, LabSession, SessionSeat, Reservation, Event, RoomLayout
import app.modules.booking.service as svc
import app.infrastructure.redis.admission as booking_queue
from app.schemas import LabInput
from fastapi import APIRouter
from app.shared.http import DB, admin
from app.modules.rooms.service import room_lock, validate_overlap
from app.modules.sessions.service import lab_dict

router = APIRouter()

@router.get('/lab-sessions')
def lab_sessions(db=DB):
    return {'items': [lab_dict(r,db) | {'session_type':db.get(Event,r.event_id).session_type if r.event_id else None} for r in db.scalars(select(LabSession).order_by(LabSession.start_at))], 'server_time':svc.now(db), 'queue_policy':booking_queue.policy(db).public()}


@router.post('/admin/lab-sessions',status_code=201)
def create_lab(data: LabInput, request: Request, db=DB):
    admin(db,request); room_lock(db,data.room_id); validate_overlap(db,data)
    lab=LabSession(**data.model_dump()); db.add(lab); db.flush()
    for seat in db.scalars(select(Seat).where(Seat.room_id==data.room_id)):
        db.add(SessionSeat(session_id=lab.id,seat_id=seat.id))
    return lab_dict(lab,db)


@router.patch('/admin/lab-sessions/{session_id}')
def edit_lab(session_id: UUID, data: LabInput, request: Request, db=DB):
    admin(db,request)
    original=db.get(LabSession,session_id)
    svc.require(original is not None,404,'not_found','Không có ca')
    svc.require(original.room_id==data.room_id,409,'room_fixed','Không chuyển phòng của ca')
    room_lock(db,data.room_id)
    lab=db.scalar(select(LabSession).where(LabSession.id==session_id).with_for_update())
    svc.require(lab is not None,404,'not_found','Không có ca')
    db.refresh(lab)
    svc.require(db.scalar(select(Reservation.id).where(Reservation.session_id==session_id).limit(1)) is None)
    validate_overlap(db,data,session_id)
    for key,value in data.model_dump().items():
        setattr(lab,key,value)
    return lab_dict(lab,db)


@router.delete('/admin/lab-sessions/{session_id}')
def delete_lab(session_id: UUID, request: Request, db=DB):
    admin(db,request)
    lab=db.get(LabSession,session_id)
    svc.require(lab is not None,404,'not_found','Không có ca')
    room_lock(db,lab.room_id)
    lab=db.scalar(select(LabSession).where(LabSession.id==session_id).with_for_update())
    svc.require(lab is not None,404,'not_found','Không có ca')
    svc.require(db.scalar(select(Reservation.id).where(Reservation.session_id==session_id).limit(1)) is None)
    for ss in db.scalars(select(SessionSeat).where(SessionSeat.session_id==session_id)):
        db.delete(ss)
    db.flush(); db.delete(lab)
    return {'status':'deleted'}


@router.get('/lab-sessions/{session_id}/seats')
def seats(session_id: UUID, db=DB):
    lab=db.get(LabSession,session_id)
    svc.require(lab is not None,404,'not_found','Không có ca')
    clock = svc.now(db)
    occupied = dict(db.execute(select(Reservation.seat_id,func.count()).where(Reservation.session_id==session_id, or_(Reservation.status.in_(('CONFIRMED','CHECKED_IN')), and_(Reservation.status=='HELD',Reservation.hold_expires_at>clock))).group_by(Reservation.seat_id)).all())
    items = db.scalars(select(Seat).join(SessionSeat, SessionSeat.seat_id==Seat.id).where(SessionSeat.session_id==session_id).order_by(Seat.seat_code))
    layout_revision=db.scalar(select(RoomLayout.revision).where(RoomLayout.room_id==lab.room_id)) or 0
    return {'server_time':clock,'next_change_at':min([t for t in [lab.close_at,__import__('app.modules.checkin.policy',fromlist=['deadline']).deadline(lab),db.scalar(select(func.min(Reservation.hold_expires_at)).where(Reservation.session_id==session_id,Reservation.status=='HELD',Reservation.hold_expires_at>clock))] if t and t>clock],default=None),'layout_revision':layout_revision,'items':[{'id':s.id,'seat_code':s.seat_code,'capacity':s.capacity,'remaining':max(0,s.capacity-occupied.get(s.id,0)),'available':occupied.get(s.id,0)<s.capacity} for s in items]}


