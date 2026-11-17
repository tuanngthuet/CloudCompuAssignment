"""Room layouts are presentation metadata; reservations remain authoritative."""
import uuid
from sqlalchemy import select
from .models import Room, Seat, LabSession, SessionSeat, Reservation, RoomLayout
from .errors import Problem

def fail(message, status=422):
    raise Problem(status, 'layout_conflict' if status==409 else 'invalid_layout', message)

from .map_geometry import default_seats, fallback, validate

def locked(db, room_id):
    return db.scalar(select(Reservation.id).join(LabSession,Reservation.session_id==LabSession.id).where(LabSession.room_id==room_id).limit(1)) is not None

def guard(db, room_id):
    list(db.scalars(select(LabSession).where(LabSession.room_id==room_id).order_by(LabSession.id).with_for_update()))
    if locked(db,room_id):fail('Sơ đồ đã có đăng kí; không thể sửa',409)

def read(db, room_id):
    seats=list(db.scalars(select(Seat).where(Seat.room_id==room_id).order_by(Seat.seat_code)))
    row=db.get(RoomLayout,room_id)
    layout=dict(row.layout) if row else fallback(seats)
    codes={str(s.id):s.seat_code for s in seats}
    layout['elements']=[dict(e,seat_code=codes.get(e.get('seat_id'),'')) if e['kind'] in ('seat','zone') else dict(e) for e in layout['elements']]
    if layout.get('type')=='image':
        layout['image_url']=f'/rooms/{room_id}/seat-map/image?v={layout["image_key"].split("/")[-1]}'
    return layout|{'revision':row.revision if row else 0,'locked':locked(db,room_id)}


def save(db, room_id, data):
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    if room is None:raise Problem(404,'not_found','Không có phòng')
    guard(db,room_id)
    row=db.get(RoomLayout,room_id)
    if data.revision!=(row.revision if row else 0):fail('Sơ đồ đã đổi; hãy tải lại',409)
    if row and row.layout.get('type')=='image':fail('Dùng trình sửa sơ đồ ảnh để thay đổi sơ đồ này',409)
    validate(data)
    current={s.id:s for s in db.scalars(select(Seat).where(Seat.room_id==room_id))}
    wanted={e.seat_id for e in data.elements if e.kind=='seat' and e.seat_id}
    if wanted-set(current):fail('Ghế không thuộc phòng')
    for sid,seat in current.items():
        if sid not in wanted:
            for ss in db.scalars(select(SessionSeat).where(SessionSeat.seat_id==sid)):db.delete(ss)
            db.flush();db.delete(seat)
        else:seat.seat_code='~'+uuid.uuid4().hex[:29]
    db.flush()
    labs=list(db.scalars(select(LabSession).where(LabSession.room_id==room_id)))
    elements=[]
    for e in data.elements:
        item=e.model_dump(mode='json')
        if e.kind=='seat':
            seat=current.get(e.seat_id)
            if seat is None:
                seat=Seat(room_id=room_id,seat_code=e.seat_code);db.add(seat);db.flush()
                for lab in labs:db.add(SessionSeat(session_id=lab.id,seat_id=seat.id))
            seat.seat_code=e.seat_code
            item['seat_id']=str(seat.id);item.pop('seat_code',None)
        elements.append(item)
    if row is None:
        row=RoomLayout(room_id=room_id,revision=0,layout={});db.add(row)
    row.layout={'columns':data.columns,'rows':data.rows,'elements':elements};row.revision+=1
    db.flush()
    return read(db,room_id)

def initialize(db,room):
    for code in default_seats():db.add(Seat(room_id=room.id,seat_code=code))
    db.flush()
    row=RoomLayout(room_id=room.id,revision=1,layout=fallback(list(db.scalars(select(Seat).where(Seat.room_id==room.id)))))
    db.add(row)
