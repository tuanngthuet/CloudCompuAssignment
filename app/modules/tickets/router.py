"""tickets HTTP API."""
import csv
import io
from uuid import UUID
from fastapi import Request, Response
from sqlalchemy import select
from app.models import Room, Seat, LabSession, Reservation, User, Event
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from fastapi import APIRouter
from app.shared.http import DB
from app.modules.tickets.service import ticket

router = APIRouter()

@router.get('/me/tickets')
def tickets(request: Request, db=DB):
    user, _ = auth.authenticate(db,request)
    clock = svc.now(db)
    items = []
    query=(select(Reservation,LabSession,Event.name,Seat.seat_code,Room.name)
        .select_from(Reservation)
        .join(LabSession,LabSession.id==Reservation.session_id)
        .outerjoin(Event,Event.id==LabSession.event_id)
        .join(Seat,Seat.id==Reservation.seat_id)
        .join(Room,Room.id==LabSession.room_id)
        .where(Reservation.user_id==user.id))
    for r,lab,event_name,seat_code,room_name in db.execute(query):
        data = ticket(r)
        data.update(event_name=event_name or room_name or 'Ca',start_at=lab.start_at,end_at=lab.end_at,seat_code=seat_code)
        if r.status == 'HELD' and r.hold_expires_at <= clock:
            data['status'] = 'EXPIRED'
        items.append(data)
    return items


@router.get('/me/tickets/{reservation_id}/qr')
def qr(reservation_id: UUID, request: Request, db=DB):
    user, _ = auth.authenticate(db,request)
    r = db.get(Reservation,reservation_id)
    svc.require(r is not None and r.user_id==user.id,404,'not_found','Không có đăng kí')
    svc.require(r.ticket_code is not None)
    import qrcode
    out = io.BytesIO()
    qrcode.make(r.ticket_code).save(out,format='PNG')
    return Response(out.getvalue(),media_type='image/png')


@router.get('/admin/lab-sessions/{session_id}/registrations.csv')
def export_csv(session_id: UUID, request: Request, db=DB):
    auth.authenticate(db,request,admin=True)
    svc.require(db.get(LabSession,session_id) is not None,404,'not_found','Không có ca')
    out=io.StringIO(); writer=csv.writer(out)
    writer.writerow(['reservation_id','username','seat_code','status','checked_in_at'])
    rows=db.execute(select(Reservation,User.username,Seat.seat_code).join(User,User.id==Reservation.user_id).join(Seat,Seat.id==Reservation.seat_id).where(Reservation.session_id==session_id))
    clock=svc.now(db)
    for r, username, code in rows:
        def safe(v):
            value=str(v or '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else value
        writer.writerow(map(safe,[r.id,username,code,'EXPIRED' if r.status=='HELD' and r.hold_expires_at<=clock else r.status,r.checked_in_at]))
    return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="registrations-{session_id}.csv"'})


