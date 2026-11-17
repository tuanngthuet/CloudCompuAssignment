"""Shared rooms application operations."""
from sqlalchemy import select
from app.models import Room, Seat, LabSession, Event, RoomLayout
import app.modules.booking.service as svc
from app import layouts

def room_lock(db, room_id):
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    svc.require(room is not None,404,'not_found','Không có phòng')
    return room


def lock_room_sessions(db, room_id):
    return list(db.scalars(select(LabSession).where(LabSession.room_id==room_id).order_by(LabSession.id).with_for_update()))


def validate_overlap(db, data, exclude=None):
    if data.event_id is not None:
        svc.require(db.get(Event, data.event_id) is not None, 404, "not_found", "Không có ca")
    q=select(LabSession.id).where(LabSession.room_id==data.room_id,LabSession.start_at<data.end_at,LabSession.end_at>data.start_at)
    if exclude:
        q=q.where(LabSession.id!=exclude)
    svc.require(db.scalar(q.limit(1)) is None,409,'overlap','Ca trùng phòng')


def sync_layout(db,room_id):
    image_layout=db.get(RoomLayout,room_id)
    svc.require(not image_layout or image_layout.layout.get('type')!='image',409,'image_map','Sửa ghế/khu trong trình sửa sơ đồ ảnh')
    row=db.get(RoomLayout,room_id)
    seats=list(db.scalars(select(Seat).where(Seat.room_id==room_id)))
    if row is None:
        row=RoomLayout(room_id=room_id,revision=0,layout=layouts.fallback(seats));db.add(row)
    existing={e.get('seat_id'):e for e in row.layout.get('elements',[]) if e['kind']=='seat'}
    # Preserve positions; append newly created seats in free cells.
    elements=[e for e in row.layout.get('elements',[]) if e['kind']!='seat' or e.get('seat_id') in {str(s.id) for s in seats}]
    occupied={(x,y) for e in elements for x in range(e['x'],e['x']+e['width']) for y in range(e['y'],e['y']+e['height'])}
    for seat in seats:
        if str(seat.id) not in existing:
            pos=next(((x,y) for y in range(40) for x in range(40) if (x,y) not in occupied),None)
            svc.require(pos is not None,409,'layout_full','Sơ đồ đã đầy')
            x,y=pos;occupied.add(pos)
            elements.append({'id':str(seat.id),'kind':'seat','seat_id':str(seat.id),'x':x,'y':y,'width':1,'height':1,'label':''})
    svc.require(len(elements)<=500,409,'layout_full','Sơ đồ tối đa 500 phần tử')
    row.layout={'columns':max([row.layout.get('columns',8)]+[e['x']+e['width'] for e in elements]),'rows':max([row.layout.get('rows',12)]+[e['y']+e['height'] for e in elements]),'elements':elements};row.revision+=1


