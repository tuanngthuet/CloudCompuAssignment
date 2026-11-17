"""rooms HTTP API."""
from uuid import UUID
from fastapi import Request, Response, UploadFile, File, Form
from sqlalchemy import select
from app.models import Room, Seat, LabSession, SessionSeat, Reservation, RoomLayout
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from app import layouts
from app.schemas import RoomInput, SeatInput, MapInput
from app.infrastructure.storage.objects import storage, normalize, new_key, MAX_BYTES
from app import image_maps
from app.image_maps import ImageMapInput
from fastapi import APIRouter
from app.shared.http import DB, admin
from app.modules.rooms.service import room_lock, lock_room_sessions, sync_layout

router = APIRouter()

@router.get('/rooms')
def rooms(db=DB):
    return [{'id':r.id,'name':r.name,'has_image':bool(r.image_key)} for r in db.scalars(select(Room).order_by(Room.name))]


@router.post('/admin/rooms/{room_id}/image')
def upload_image(room_id: UUID, request: Request, file: UploadFile=File(...), db=DB):
    auth.authenticate(db,request,write=True,admin=True)
    room=db.scalar(select(Room).where(Room.id==room_id).with_for_update())
    svc.require(room is not None,404,'not_found','Không có phòng')
    data=normalize(file.file.read(MAX_BYTES+1))
    key=new_key(); backend=storage()
    try:
        backend.put(key,data)
    except Exception:
        raise svc.Problem(503,'storage_unavailable','Không thể lưu ảnh') from None
    from app.infrastructure.storage.registry import track
    track(db,key,True)
    room.image_key=key
    # Keep old objects until an explicit maintenance task; deleting before commit is unsafe.
    return {'room_id':room.id,'image_url':f'/rooms/{room.id}/image'}


@router.get('/rooms/{room_id}/image')
def read_image(room_id: UUID, db=DB):
    room=db.get(Room,room_id)
    svc.require(room is not None and room.image_key is not None,404,'not_found','Không có ảnh')
    try:
        data=storage().get(room.image_key)
    except FileNotFoundError:
        raise svc.Problem(404,'not_found','Không có ảnh') from None
    except Exception:
        raise svc.Problem(503,'storage_unavailable','Không thể đọc ảnh') from None
    return Response(data,media_type='image/jpeg')


@router.post('/admin/rooms',status_code=201)
def create_room(data: RoomInput, request: Request, db=DB):
    admin(db,request)
    room=Room(name=data.name); db.add(room); db.flush(); layouts.initialize(db,room)
    return {'id':room.id,'name':room.name}


@router.patch('/admin/rooms/{room_id}')
def edit_room(room_id: UUID, data: RoomInput, request: Request, db=DB):
    admin(db,request); room=room_lock(db,room_id); room.name=data.name
    return {'id':room.id,'name':room.name}


@router.delete('/admin/rooms/{room_id}')
def delete_room(room_id: UUID, request: Request, db=DB):
    admin(db,request); room=room_lock(db,room_id)
    svc.require(db.scalar(select(LabSession.id).where(LabSession.room_id==room_id).limit(1)) is None)
    for seat in db.scalars(select(Seat).where(Seat.room_id==room_id)):
        db.delete(seat)
    db.flush(); db.delete(room)
    return {'status':'deleted'}


@router.get('/admin/rooms/{room_id}/seats')
def room_seats(room_id: UUID, request: Request, db=DB):
    auth.authenticate(db,request,admin=True)
    svc.require(db.get(Room,room_id) is not None,404,'not_found','Không có phòng')
    return [{'id':s.id,'seat_code':s.seat_code} for s in db.scalars(select(Seat).where(Seat.room_id==room_id).order_by(Seat.seat_code))]


@router.post('/admin/rooms/{room_id}/seats',status_code=201)
def create_seat(room_id: UUID, data: SeatInput, request: Request, db=DB):
    admin(db,request); room_lock(db,room_id)
    existing_map=db.get(RoomLayout,room_id)
    svc.require(not existing_map or existing_map.layout.get('type')!='image',409,'image_map','Sửa ghế/khu trong trình sửa sơ đồ ảnh')
    labs=lock_room_sessions(db,room_id); layouts.guard(db,room_id)
    seat=Seat(room_id=room_id,seat_code=data.seat_code); db.add(seat); db.flush()
    for lab in labs:
        db.add(SessionSeat(session_id=lab.id,seat_id=seat.id))
    db.flush(); sync_layout(db,room_id)
    return {'id':seat.id,'seat_code':seat.seat_code}


@router.delete('/admin/rooms/{room_id}/seats/{seat_id}')
def delete_seat(room_id: UUID, seat_id: UUID, request: Request, db=DB):
    admin(db,request); room_lock(db,room_id); lock_room_sessions(db,room_id); layouts.guard(db,room_id)
    seat=db.get(Seat,seat_id)
    svc.require(seat is not None and seat.room_id==room_id,404,'not_found','Không có chỗ')
    svc.require(db.scalar(select(Reservation.id).where(Reservation.seat_id==seat_id).limit(1)) is None)
    for ss in db.scalars(select(SessionSeat).where(SessionSeat.seat_id==seat_id)):
        db.delete(ss)
    db.flush(); db.delete(seat); db.flush(); sync_layout(db,room_id)
    return {'status':'deleted'}


@router.patch('/admin/rooms/{room_id}/seats/{seat_id}')
def edit_seat(room_id: UUID, seat_id: UUID, data: SeatInput, request: Request, db=DB):
    admin(db,request); room_lock(db,room_id); lock_room_sessions(db,room_id); layouts.guard(db,room_id)
    seat=db.get(Seat,seat_id)
    svc.require(seat is not None and seat.room_id==room_id,404,'not_found','Không có chỗ')
    svc.require(db.scalar(select(Reservation.id).where(Reservation.seat_id==seat_id).limit(1)) is None)
    seat.seat_code=data.seat_code
    db.flush(); sync_layout(db,room_id)
    return {'id':seat.id,'seat_code':seat.seat_code}


@router.get('/rooms/{room_id}/seat-map')
def seat_map(room_id: UUID, db=DB):
    svc.require(db.get(Room,room_id) is not None,404,'not_found','Không có phòng')
    return layouts.read(db,room_id)


@router.put('/admin/rooms/{room_id}/seat-map')
def save_seat_map(room_id: UUID, data: MapInput, request: Request, db=DB):
    admin(db,request)
    return layouts.save(db,room_id,data)


@router.post('/admin/rooms/{room_id}/seat-map/image')
def detect_image_map(room_id: UUID, request: Request, file: UploadFile=File(...), min_area: int=Form(400,ge=16,le=10000), db=DB):
    admin(db,request)
    return image_maps.upload(db,room_id,file.file.read(MAX_BYTES+1),min_area)


@router.put('/admin/rooms/{room_id}/seat-map/image')
def save_image_map(room_id: UUID, data: ImageMapInput, request: Request, db=DB):
    admin(db,request)
    return image_maps.save(db,room_id,data)


@router.get('/rooms/{room_id}/seat-map/image')
def read_map_image(room_id: UUID, request: Request, key: str | None=None, db=DB):
    row=db.get(RoomLayout,room_id)
    published=row.layout.get('image_key') if row else None
    key=key or published
    svc.require(key is not None and image_maps.valid_key(room_id,key),404,'not_found','Không có ảnh sơ đồ')
    if key!=published:auth.authenticate(db,request,admin=True)
    try:data=storage().get(key)
    except FileNotFoundError:raise svc.Problem(404,'not_found','Không có ảnh sơ đồ') from None
    except Exception:raise svc.Problem(503,'storage_unavailable','Không thể tải ảnh sơ đồ') from None
    headers = {}
    if 'key' not in request.query_params and request.query_params.get('v') == published.rsplit('/', 1)[-1]:
        headers['Cache-Control'] = 'public, max-age=86400'
    return Response(data,media_type='image/png',headers=headers)


