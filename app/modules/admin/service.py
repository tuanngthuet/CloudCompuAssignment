"""Shared admin application operations."""
import uuid
from sqlalchemy import select
from app.models import Room, LabSession, Reservation, Event, RoomLayout
import app.modules.booking.service as svc
from app.schemas import LabInput, EventInput
from app.infrastructure.storage.objects import storage, normalize_poster, MAX_BYTES
from app.shared.http import admin
from app.modules.rooms.service import room_lock, validate_overlap
from app.modules.sessions.service import lab_dict

def save_event_schedule(db,event,schedule):
    if schedule is None:
        return
    labs=list(db.scalars(select(LabSession).where(LabSession.event_id==event.id).order_by(LabSession.id)))
    svc.require(len(labs)<=1,409,'multiple_schedules','Ca có nhiều lịch; cần hợp nhất trước khi sửa')
    if labs:
        room_lock(db,labs[0].room_id)
        lab=db.scalar(select(LabSession).where(LabSession.id==labs[0].id).with_for_update())
        db.refresh(lab)
        changed=any(getattr(lab,key)!=value for key,value in schedule.model_dump().items())
        if changed:
            validate_overlap(db,LabInput(room_id=lab.room_id,event_id=event.id,**schedule.model_dump()),lab.id)
            svc.require(db.scalar(select(Reservation.id).where(Reservation.session_id==lab.id).limit(1)) is None,409,'schedule_locked','Đã có đăng kí; không thể đổi lịch')
            for key,value in schedule.model_dump().items():setattr(lab,key,value)
    else:
        room=Room(name=event.name);db.add(room);db.flush()
        db.add(RoomLayout(room_id=room.id,revision=0,layout={'columns':8,'rows':12,'elements':[]}))
        lab=LabSession(event_id=event.id,room_id=room.id,**schedule.model_dump());db.add(lab)
    db.flush()


def event_dict(event, db):
    result = {key: getattr(event, key) for key in ('id', 'name', 'session_type', 'description', 'venue', 'address','status')}
    for slot in ('poster',):
        result[slot + '_url'] = f'/events/{event.id}/images/{slot}?v={getattr(event, slot + "_key").split("/")[-1]}' if getattr(event, slot + '_key') else None
    lab=db.scalar(select(LabSession).where(LabSession.event_id==event.id).order_by(LabSession.start_at,LabSession.id).limit(1))
    result['schedule']=lab_dict(lab,db) if lab else None
    return result


def parse_ca(data):
    from pydantic import ValidationError
    try:
        return EventInput.model_validate_json(data)
    except ValidationError:
        raise svc.Problem(422, 'invalid_input', 'Thông tin ca không hợp lệ') from None


def persist_ca(db, request, data, poster, event=None):
    admin(db, request)
    parsed = parse_ca(data)
    creating = event is None
    svc.require(not creating or parsed.schedule is not None,422,'schedule_required','Nhập lịch ca')
    svc.require(not creating or poster is not None,422,'poster_required','Tải ảnh cho ca')
    image = normalize_poster(poster.file.read(MAX_BYTES+1)) if poster else None
    if creating:
        event = Event(**parsed.model_dump(exclude={'schedule'}))
        db.add(event); db.flush()
    else:
        for key,value in parsed.model_dump(exclude={'schedule'}).items():setattr(event,key,value)
    save_event_schedule(db,event,parsed.schedule)
    if image is not None:
        key=f'events/{event.id}/poster/{uuid.uuid4()}.jpg'
        try:
            storage().put(key,image)
        except Exception:
            raise svc.Problem(503,'storage_unavailable','Chưa lưu được ảnh ca. Hãy thử lại.') from None
        from app.infrastructure.storage.registry import track
        track(db,key,True)
        event.poster_key=key
    return event_dict(event,db)


