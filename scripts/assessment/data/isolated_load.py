"""Separate, backup-gated load fixture. Defaults to plan-only; never edits demo rows."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time
from uuid import NAMESPACE_URL,UUID,uuid5

from fastapi import Response
from sqlalchemy import delete,func,or_,select,text
from app.infrastructure.database.session import Session
from app.models import (AdminAudit,AuditEvent,AuthChallenge,EmailJob,Event,IdempotencyRecord,
    LabSession,LoginSession,NotificationDelivery,OutboxEvent,PlatformEvent,Reservation,
    Room,RoomLayout,Seat,SessionSeat,StaffAssignment,User,WebhookInbox)
from app.modules.auth import service as auth
from app.modules.booking.service import now
from demo_backup import fingerprint

PHYSICS_ROOM=UUID('5287d90a-0163-599b-a753-57bfb86023bc')
MECHANIC_ROOM=UUID('6109bc54-94ca-587a-abae-012152b5c769')
MECHANIC_EVENT=UUID('35f3e9ce-9e36-5345-90eb-40b38b5d6dc6')


def private(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.'+secrets.token_hex(4))
    with os.fdopen(os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(value,stream,indent=2,ensure_ascii=False)
    temporary.replace(path)


class Scope:
    def __init__(self,name):
        if not re.fullmatch(r'demo-load-[a-z0-9-]{6,24}',name):raise ValueError('Use a dedicated demo-load-* namespace')
        self.name=name
        self.users=[self.id(f'user-{i}') for i in range(100)]
        self.seats=[self.id(f'seat-{i}') for i in range(120)]
        self.room,self.event,self.lab=self.id('room'),self.id('event'),self.id('lab')
    def id(self,key):return uuid5(NAMESPACE_URL,'labseat-isolated-load:'+self.name+':'+key)
    def username(self,i):return self.name+f'-s{i+1:03}'
    def password(self,master,i):return hmac.new(master.encode(),self.username(i).encode(),hashlib.sha256).hexdigest()[:32]


def verify_demo(db,backup,local=False):
    url=db.get_bind().url
    if local:
        if os.getenv('APP_ENV')!='test' or url.host!='backup-verify-db' or not url.database.endswith('_test'):
            raise ValueError('Local verification is restricted to the disposable restored DB')
    elif url.host!=backup['expected_host'] or url.query.get('sslmode')!='verify-full':
        raise ValueError('Wrong source database or missing TLS verification')
    baseline_path=Path(backup['_directory'])/backup['source_fingerprint']
    if hashlib.sha256(baseline_path.read_bytes()).hexdigest()!=backup['source_fingerprint_sha256']:
        raise ValueError('Backup fingerprint file changed')
    original=json.loads(baseline_path.read_text())
    if backup.get('demo_fingerprint'):
        demo_path=Path(backup['_directory'])/backup['demo_fingerprint']
        if hashlib.sha256(demo_path.read_bytes()).hexdigest()!=backup['demo_fingerprint_sha256']:
            raise ValueError('Demo business baseline file changed')
        original=json.loads(demo_path.read_text())
    current=fingerprint(db.connection().connection.driver_connection,original)
    expected={key:original['tables'][key] for key in current['tables']}
    if current['tables']!=expected:raise RuntimeError('Demo rows changed since backup; refresh backup before preparing load')
    if current['schema_revision']!=original['schema_revision'] or current['constraints_sha256']!=original['constraints_sha256']:
        raise RuntimeError('Schema/constraints changed since backup; inspect before continuing')
    return {'verified':True,'tables':len(current['tables']),'invariant_rows':current['invariant_rows'],'db_clock':current['db_clock']}


def owned(db,scope,complete=False):
    for i,uid in enumerate(scope.users):
        user=db.get(User,uid)
        if user and (user.username!=scope.username(i) or user.role!='student' or user.email!=scope.username(i)+'@example.invalid'):
            raise RuntimeError('Load user ownership mismatch')
        if complete and not user:raise RuntimeError('Missing load user')
    event=db.get(Event,scope.event);room=db.get(Room,scope.room);lab=db.get(LabSession,scope.lab)
    if event and (event.session_type!='practice' or scope.name not in event.description):raise RuntimeError('Event ownership mismatch')
    if room and scope.name not in room.name:raise RuntimeError('Room ownership mismatch')
    if lab and (lab.event_id!=scope.event or lab.room_id!=scope.room):raise RuntimeError('Schedule ownership mismatch')
    if complete and not all((event,room,lab)):raise RuntimeError('Incomplete load fixture')
    layout=db.get(RoomLayout,scope.room)
    artwork=layout.layout.get('assessment_artwork') if layout else None
    physics=artwork=='load-physics'
    mechanic=artwork=='load-mechanic'
    expected=scope.seats[:4] if mechanic else scope.seats[:34] if physics else scope.seats
    capacity=45 if physics or mechanic else 1
    seats=list(db.scalars(select(Seat).where(Seat.room_id==scope.room)))
    if any(s.id not in expected or s.capacity!=capacity for s in seats):raise RuntimeError('Seat ownership/capacity mismatch')
    if complete and {s.id for s in seats}!=set(expected):raise RuntimeError('Load capacity is incomplete')
    if physics and (layout.layout.get('source_room_id')!=str(PHYSICS_ROOM)
            or {e['seat_id'] for e in layout.layout['elements']}!=set(map(str,expected))):
        raise RuntimeError('Physics load layout ownership mismatch')
    if mechanic and (layout.layout.get('source_room_id')!=str(MECHANIC_ROOM)
            or {e['seat_id'] for e in layout.layout['elements']}!=set(map(str,expected))):
        raise RuntimeError('Mechanic load layout ownership mismatch')


def load_seats(db,scope):
    rows={s.id:s for s in db.scalars(select(Seat).where(Seat.room_id==scope.room))}
    return [rows[sid] for sid in scope.seats if sid in rows]


def assign_seats(seats,occupied,count=100):
    remaining={seat['seat_id']:seat['capacity']-occupied.get(UUID(seat['seat_id']),0) for seat in seats}
    result=[]
    while len(result)<count:
        before=len(result)
        for seat in seats:
            sid=seat['seat_id']
            if remaining[sid]>0:
                result.append(UUID(sid));remaining[sid]-=1
                if len(result)==count:return result
        if len(result)==before:raise RuntimeError('Insufficient remaining capacity for the handoff')
    return result


def prepare(db,scope,master,close_at):
    owned(db,scope)
    layout=db.get(RoomLayout,scope.room)
    if layout and layout.layout.get('assessment_artwork') in ('load-physics','load-mechanic'):
        owned(db,scope,complete=True);return
    clock=now(db)
    if close_at.tzinfo is None or close_at<clock+timedelta(hours=4):raise ValueError('Load window must cover at least four hours')
    for i,uid in enumerate(scope.users):
        if not db.get(User,uid):
            db.add(User(id=uid,username=scope.username(i),role='student',
                password_hash=auth.hasher.hash(scope.password(master,i)),
                full_name=f'Tài khoản tải {i+1:03}',cccd=f'98{uid.int%10**10:010}',
                email=scope.username(i)+'@example.invalid',email_verified_at=clock))
    if not db.get(Room,scope.room):db.add(Room(id=scope.room,name='['+scope.name+'] Phòng chịu tải riêng'))
    if not db.get(Event,scope.event):db.add(Event(id=scope.event,name=f'Ca chịu tải riêng [{scope.name}] (không dùng demo)',
        session_type='practice',status='ACTIVE',description='Synthetic load fixture; namespace='+scope.name,
        venue='Khu vực kiểm thử tách riêng',address='Synthetic — không phải địa điểm thi thật'))
    db.flush()
    for i,sid in enumerate(scope.seats):
        if not db.get(Seat,sid):db.add(Seat(id=sid,room_id=scope.room,seat_code=f'L{i+1:03}',capacity=1))
    db.flush()
    if not db.get(RoomLayout,scope.room):
        elements=[{'id':str(scope.id('board')),'kind':'board','x':0,'y':0,'width':12,'height':1,'label':'CA TẢI RIÊNG — KHÔNG DÙNG DEMO'}]
        elements += [{'id':str(sid),'kind':'seat','seat_id':str(sid),'x':i%12,'y':1+i//12,'width':1,'height':1,'label':f'L{i+1:03}'} for i,sid in enumerate(scope.seats)]
        db.add(RoomLayout(room_id=scope.room,revision=1,layout={'columns':12,'rows':11,'elements':elements}))
    if not db.get(LabSession,scope.lab):
        db.add(LabSession(id=scope.lab,event_id=scope.event,room_id=scope.room,open_at=clock-timedelta(minutes=5),
            close_at=close_at,start_at=close_at+timedelta(hours=1),end_at=close_at+timedelta(hours=3),checkin_enabled=False))
    db.flush()
    for i,sid in enumerate(scope.seats):
        key=scope.id(f'schedule-seat-{i}')
        if not db.get(SessionSeat,key):db.add(SessionSeat(id=key,session_id=scope.lab,seat_id=sid))
    db.flush();owned(db,scope,complete=True)


def manifest(db,scope):
    owned(db,scope,complete=True);lab=db.get(LabSession,scope.lab)
    seats=load_seats(db,scope)
    layout=db.get(RoomLayout,scope.room)
    return {'batch':scope.name,'manifest_id':str(scope.id('manifest')),'event_id':str(scope.event),
        'load_session':str(scope.lab),'room_id':str(scope.room),'users':[{'id':str(uid),'username':scope.username(i),'role':'student'} for i,uid in enumerate(scope.users)],
        'seats':[{'seat_id':str(seat.id),'code':seat.seat_code,'capacity':seat.capacity} for seat in seats],
        'capacity':sum(seat.capacity for seat in seats),'layout_type':layout.layout.get('type','grid'),
        'layout_revision':layout.revision,'open_at':lab.open_at.isoformat(),'close_at':lab.close_at.isoformat(),
        'start_at':lab.start_at.isoformat(),'end_at':lab.end_at.isoformat(),'checkin_enabled':False}


def sessions(db,scope,minimum):
    data=manifest(db,scope);lab=db.get(LabSession,scope.lab);clock=now(db)
    if not lab.open_at<=clock or lab.close_at<clock+timedelta(seconds=minimum) or lab.start_at<=clock+timedelta(seconds=minimum):
        raise RuntimeError('Load schedule no longer covers the measurement window')
    if db.get(Event,scope.event).status!='ACTIVE':raise RuntimeError('Load event is not active')
    occupied=dict(db.execute(select(Reservation.seat_id,func.count()).where(Reservation.session_id==scope.lab,
        or_(Reservation.status.in_(('CONFIRMED','CHECKED_IN')),(Reservation.status=='HELD')&(Reservation.hold_expires_at>clock))).group_by(Reservation.seat_id)).all())
    if db.scalar(select(Reservation.id).where(Reservation.session_id==scope.lab,Reservation.user_id.in_(scope.users),
            or_(Reservation.status.in_(('CONFIRMED','CHECKED_IN')),(Reservation.status=='HELD')&(Reservation.hold_expires_at>clock))).limit(1)):
        raise RuntimeError('A load account already has an active reservation')
    assigned=assign_seats(data['seats'],occupied)
    codes={seat['seat_id']:seat['code'] for seat in data['seats']}
    result=[];expires=[]
    for i,uid in enumerate(scope.users):
        user=db.get(User,uid);seat=assigned[i]
        if user.status!='ACTIVE' or not user.email_verified_at or user.pending_email:raise RuntimeError('Load user is unavailable')
        old=db.get(LoginSession,scope.id(f'login-{i}'))
        if old and old.user_id!=uid:raise RuntimeError('Session ownership mismatch')
        if old:db.delete(old);db.flush()
        response=Response();identity=auth.create_session(db,user,response)
        row=next(x for x in db.new if isinstance(x,LoginSession));row.id=scope.id(f'login-{i}')
        if row.expires_at<clock+timedelta(seconds=minimum):raise RuntimeError('App session TTL is too short')
        cookie=next(value for name,value in response.raw_headers if name==b'set-cookie' and value.startswith(b'labseat_session='))
        token=cookie.decode().split(';',1)[0].split('=',1)[1]
        result.append({'session_token':token,'csrf_token':identity['csrf_token'],'seat_id':str(seat),'expires_at':row.expires_at.isoformat()})
        expires.append(row.expires_at);db.flush()
    data.update(sessions_expire_at=(min(expires)-timedelta(seconds=1)).isoformat(),minimum_valid_seconds=minimum,issued_at_server=clock.isoformat())
    data['mapping']=[{'session_index':i,'user_id':str(uid),'username':scope.username(i),
        'event_id':str(scope.event),'load_session':str(scope.lab),'room_id':str(scope.room),
        'seat_id':str(assigned[i]),'seat_code':codes[str(assigned[i])]} for i,uid in enumerate(scope.users)]
    return data,result


def physics_map(db,scope,output):
    """Copy the demo Physics presentation into the owned, idle load room only."""
    from app.infrastructure.storage.objects import storage
    from app.infrastructure.storage.registry import track
    owned(db,scope,complete=True)
    lab=db.scalar(select(LabSession).where(LabSession.id==scope.lab).with_for_update())
    target=db.scalar(select(RoomLayout).where(RoomLayout.room_id==scope.room).with_for_update())
    source=db.get(RoomLayout,PHYSICS_ROOM)
    if not source or source.layout.get('type')!='image':raise RuntimeError('Physics source layout is missing')
    zones=source.layout['elements']
    if len(zones)!=34 or any(z['kind']!='zone' for z in zones):raise RuntimeError('Unexpected Physics source regions')
    if {z['label'].split(' ')[0] for z in zones}!={f'HN{i}' for i in range(582,616)}:
        # Labels may also put the physical room first; require the HN code anywhere.
        if {re.search(r'HN\d+',z['label']).group() for z in zones if re.search(r'HN\d+',z['label'])}!={f'HN{i}' for i in range(582,616)}:
            raise RuntimeError('Physics room codes changed')
    old=list(db.scalars(select(Reservation).where(Reservation.session_id==scope.lab)))
    if any(row.user_id not in scope.users or row.status not in ('CANCELLED','EXPIRED') for row in old):
        raise RuntimeError('Load room must have no live or foreign reservations before changing its map')
    if any(row.seat_id not in scope.seats[:34] for row in old):raise RuntimeError('A removed seat has reservation history')
    if db.scalar(select(SessionSeat.id).where(SessionSeat.seat_id.in_(scope.seats),SessionSeat.session_id!=scope.lab).limit(1)):
        raise RuntimeError('A foreign schedule references load seats')
    source_hash=hashlib.sha256(json.dumps(source.layout,sort_keys=True).encode()).hexdigest()
    if target.layout.get('assessment_artwork')=='load-physics':
        if target.layout.get('source_layout_sha256')!=source_hash:raise RuntimeError('Physics source changed after the load copy')
        return {'unchanged':True,'source_layout_sha256':source_hash,'capacity':1530,'zones':34}
    private(output/'physics-map-before.private.json',{'layout':target.layout,'revision':target.revision,
        'seats':[{'id':str(s.id),'code':s.seat_code,'capacity':s.capacity} for s in load_seats(db,scope)],
        'reservations':[{'id':str(r.id),'seat_id':str(r.seat_id),'status':r.status} for r in old]})
    backend=storage();body=backend.get(source.layout['image_key']);digest=hashlib.sha256(body).hexdigest()
    key=f'rooms/{scope.room}/maps/{scope.id("physics-image-"+digest)}.png'
    backend.put(key,body,content_type='image/png')
    if hashlib.sha256(backend.get(key)).hexdigest()!=digest:raise RuntimeError('Load image copy readback failed')
    track(db,key,True)
    copied=deepcopy(source.layout)
    for i,zone in enumerate(copied['elements']):
        seat=db.get(Seat,scope.seats[i]);seat.seat_code=zone['label'];seat.capacity=45
        zone.update(id=str(scope.id(f'physics-zone-{i}')),seat_id=str(seat.id),capacity=45)
    db.execute(delete(SessionSeat).where(SessionSeat.session_id==scope.lab,SessionSeat.seat_id.in_(scope.seats[34:])))
    db.execute(delete(Seat).where(Seat.room_id==scope.room,Seat.id.in_(scope.seats[34:])))
    copied.update(image_key=key,assessment_artwork='load-physics',source_room_id=str(PHYSICS_ROOM),source_layout_sha256=source_hash)
    target.layout=copied;target.revision+=1;db.flush();owned(db,scope,complete=True)
    if hashlib.sha256(json.dumps(source.layout,sort_keys=True).encode()).hexdigest()!=source_hash:raise RuntimeError('Physics source was modified')
    return {'source_room_id':str(PHYSICS_ROOM),'source_layout_sha256':source_hash,'image_sha256':digest,
        'image_bytes':len(body),'zones':34,'capacity':1530,'preserved_cancelled_reservations':len(old),'source_unchanged':True}


def mechanic_map(db,scope,output):
    """Copy existing Mechanic artwork into a separate owned load fixture."""
    from app.infrastructure.storage.objects import storage
    from app.infrastructure.storage.registry import track
    owned(db,scope,complete=True)
    source=db.get(RoomLayout,MECHANIC_ROOM)
    source_event=db.get(Event,MECHANIC_EVENT)
    target=db.get(RoomLayout,scope.room,with_for_update=True)
    event=db.get(Event,scope.event,with_for_update=True)
    lab=db.get(LabSession,scope.lab,with_for_update=True)
    if (not source or source.layout.get('assessment_artwork')!='mechanic'
            or not source_event or not source_event.poster_key):
        raise RuntimeError('Existing Mechanic poster/map is required')
    zones=source.layout['elements']
    if len(zones)!=4 or any(z['kind']!='zone' for z in zones):
        raise RuntimeError('Expected four Mechanic source rooms')
    source_seats=list(db.scalars(select(Seat).where(Seat.room_id==MECHANIC_ROOM)))
    if len(source_seats)!=4 or any(s.capacity!=17 for s in source_seats):
        raise RuntimeError('Mechanic demo capacities must remain 17')
    old=list(db.scalars(select(Reservation).where(Reservation.session_id==scope.lab)))
    if any(r.user_id not in scope.users or r.status not in ('CANCELLED','EXPIRED') for r in old):
        raise RuntimeError('Load map requires no live or foreign reservations')
    if any(r.seat_id not in scope.seats[:4] for r in old):
        raise RuntimeError('A removed load seat has history')
    if db.scalar(select(SessionSeat.id).where(SessionSeat.seat_id.in_(scope.seats),SessionSeat.session_id!=scope.lab).limit(1)):
        raise RuntimeError('Foreign schedule references load seats')
    source_hash=hashlib.sha256(json.dumps(source.layout,sort_keys=True).encode()).hexdigest()
    if target.layout.get('assessment_artwork')=='load-mechanic':
        if target.layout.get('source_layout_sha256')!=source_hash:
            raise RuntimeError('Mechanic source changed after copying')
        return {'unchanged':True,'zones':4,'capacity':180,'source_unchanged':True}
    private(output/'mechanic-map-before.private.json',{'layout':target.layout,'revision':target.revision,
        'event_name':event.name,'event_description':event.description,'poster_key':event.poster_key,
        'seats':[{'id':str(s.id),'code':s.seat_code,'capacity':s.capacity} for s in load_seats(db,scope)]})
    backend=storage();image=backend.get(source.layout['image_key']);poster=backend.get(source_event.poster_key)
    image_hash=hashlib.sha256(image).hexdigest();poster_hash=hashlib.sha256(poster).hexdigest()
    image_key=f'rooms/{scope.room}/maps/{scope.id("mechanic-image-"+image_hash)}.png'
    poster_key=f'events/{scope.event}/poster/{scope.id("mechanic-poster-"+poster_hash)}.jpg'
    for key,body,mime in [(image_key,image,'image/png'),(poster_key,poster,'image/jpeg')]:
        backend.put(key,body,content_type=mime)
        if hashlib.sha256(backend.get(key)).hexdigest()!=hashlib.sha256(body).hexdigest():
            raise RuntimeError('Mechanic asset copy readback failed')
        track(db,key,True)
    copied=deepcopy(source.layout)
    for i,z in enumerate(copied['elements']):
        seat=db.get(Seat,scope.seats[i]);seat.seat_code=z['label'];seat.capacity=45
        z.update(id=str(scope.id(f'mechanic-zone-{i}')),seat_id=str(seat.id),capacity=45)
    db.execute(delete(SessionSeat).where(SessionSeat.session_id==scope.lab,SessionSeat.seat_id.in_(scope.seats[4:])))
    db.execute(delete(Seat).where(Seat.room_id==scope.room,Seat.id.in_(scope.seats[4:])))
    copied.update(image_key=image_key,assessment_artwork='load-mechanic',source_room_id=str(MECHANIC_ROOM),source_layout_sha256=source_hash)
    target.layout=copied;target.revision+=1
    event.name=f'Mechanic — Ca chịu tải riêng [{scope.name}]'
    event.description=('Synthetic load fixture; namespace='+scope.name+
        '. Poster/sơ đồ sao chép từ Mechanic demo, không dùng phòng/lịch demo. '+
        'Ca tải: 4 phòng ×45 =180 suất. Số 17 thí sinh in trong ảnh là cấu hình demo gốc, không phải capacity ca tải. '+
        'Email disabled; chỉ chạy trong cửa sổ đã phối hợp.')
    event.poster_key=poster_key
    db.flush();owned(db,scope,complete=True)
    if hashlib.sha256(json.dumps(source.layout,sort_keys=True).encode()).hexdigest()!=source_hash:
        raise RuntimeError('Mechanic demo source changed')
    return {'source_room_id':str(MECHANIC_ROOM),'source_event_id':str(MECHANIC_EVENT),
        'source_layout_sha256':source_hash,'image_sha256':image_hash,'poster_sha256':poster_hash,
        'zones':4,'capacity':180,'source_capacity':68,'source_unchanged':True,
        'preserved_cancelled_reservations':len(old)}


def cleanup(db,scope,execute=False):
    owned(db,scope)
    if db.scalar(select(Reservation.id).where(Reservation.user_id.in_(scope.users)!= (Reservation.session_id==scope.lab)).limit(1)):
        raise RuntimeError('Cross-scope reservations exist; cleanup refused')
    if db.scalar(select(LabSession.id).where(LabSession.id!=scope.lab,or_(LabSession.room_id==scope.room,LabSession.event_id==scope.event)).limit(1)):
        raise RuntimeError('A foreign schedule references the load room/event')
    if db.scalar(select(StaffAssignment.user_id).where(StaffAssignment.session_id==scope.lab,StaffAssignment.user_id.not_in(scope.users)).limit(1)):
        raise RuntimeError('A foreign staff assignment exists; cleanup refused')
    if db.scalar(select(SessionSeat.id).where(SessionSeat.seat_id.in_(scope.seats),SessionSeat.session_id!=scope.lab).limit(1)):
        raise RuntimeError('A foreign schedule references load seats')
    reservations=list(db.scalars(select(Reservation.id).where(Reservation.session_id==scope.lab)))
    jobs=list(db.scalars(select(EmailJob.id).where(EmailJob.user_id.in_(scope.users))))
    before={'users':db.scalar(select(func.count()).select_from(User).where(User.id.in_(scope.users))),
        'events':int(db.get(Event,scope.event) is not None),'schedules':int(db.get(LabSession,scope.lab) is not None),'seats':db.scalar(select(func.count()).select_from(Seat).where(Seat.id.in_(scope.seats))),'reservations':len(reservations)}
    if execute:
        for query in (delete(WebhookInbox).where(WebhookInbox.job_id.in_(jobs)),
            delete(PlatformEvent).where(or_(PlatformEvent.subject_id.in_(jobs),PlatformEvent.subject_id==scope.lab)),
            delete(EmailJob).where(EmailJob.id.in_(jobs)),delete(NotificationDelivery).where(NotificationDelivery.reservation_id.in_(reservations)),
            delete(OutboxEvent).where(OutboxEvent.reservation_id.in_(reservations)),delete(AuditEvent).where(AuditEvent.reservation_id.in_(reservations)),
            delete(Reservation).where(Reservation.id.in_(reservations)),delete(StaffAssignment).where(StaffAssignment.session_id==scope.lab),
            delete(SessionSeat).where(SessionSeat.session_id==scope.lab),delete(LabSession).where(LabSession.id==scope.lab),
            delete(RoomLayout).where(RoomLayout.room_id==scope.room),delete(Seat).where(Seat.id.in_(scope.seats)),
            delete(Room).where(Room.id==scope.room),delete(Event).where(Event.id==scope.event),
            delete(LoginSession).where(LoginSession.user_id.in_(scope.users)),delete(AuthChallenge).where(AuthChallenge.user_id.in_(scope.users)),
            delete(IdempotencyRecord).where(IdempotencyRecord.user_id.in_(scope.users)),
            delete(AdminAudit).where(AdminAudit.actor_id.in_(scope.users)),delete(User).where(User.id.in_(scope.users))):db.execute(query)
    return {'execute':execute,'before':before,'manifest_id':str(scope.id('manifest')),'foreign_reference_checks':'PASS'}


def smoke(scope,output,minimum,master):
    import httpx
    from io import BytesIO
    from PIL import Image
    data=json.loads((output/'manifest.json').read_text())
    identities=json.loads((output/'synthetic-sessions.json').read_text())
    if len(identities)!=100 or any(len({item[key] for item in identities})!=100 for key in ('session_token','csrf_token')):
        raise RuntimeError('Require 100 distinct user sessions and CSRF tokens')
    assignments=Counter(item['seat_id'] for item in identities)
    expiry=datetime.fromisoformat(data['sessions_expire_at'])
    if expiry<datetime.now(timezone.utc)+timedelta(seconds=minimum):raise RuntimeError('Session handoff no longer covers the requested window')
    result={'started_at_utc':datetime.now(timezone.utc).isoformat(),'base_url':'https://labseat.id.vn'}
    rid=None
    with httpx.Client(base_url=result['base_url'],timeout=20) as client:
        listing=client.get('/lab-sessions');listing.raise_for_status()
        clock=datetime.fromisoformat(listing.json()['server_time'])
        selected=next(x for x in listing.json()['items'] if x['id']==str(scope.lab))
        if not datetime.fromisoformat(selected['open_at'])<=clock<datetime.fromisoformat(selected['close_at'])-timedelta(seconds=minimum):raise RuntimeError('Load window is not ready')
        available=client.get(f'/lab-sessions/{scope.lab}/seats');available.raise_for_status()
        seats={x['id']:x for x in available.json()['items']}
        if set(seats)!={item['seat_id'] for item in data['seats']} or any(seats[item['seat_id']]['capacity']!=item['capacity'] for item in data['seats']):raise RuntimeError('Seat mapping/capacity mismatch')
        if any(sid not in seats or count>seats[sid]['remaining'] for sid,count in assignments.items()):raise RuntimeError('Assigned users exceed remaining room capacity')
        seen=set()
        for i,identity in enumerate(identities):
            client.cookies.clear();client.cookies.set('labseat_session',identity['session_token'])
            me=client.get('/me');me.raise_for_status();user=me.json()
            if user['id']!=str(scope.users[i]) or user['role']!='student' or user['account_status']!='ACTIVE' or not user['email_verified'] or user['id'] in seen:raise RuntimeError('Live user identity mismatch')
            if not seats[identity['seat_id']]['available']:raise RuntimeError('An assigned seat is unavailable')
            seen.add(user['id'])
        layout=client.get(f'/rooms/{scope.room}/seat-map');layout.raise_for_status()
        if {item['seat_id'] for item in layout.json()['elements'] if item['kind'] in ('seat','zone')}!=set(seats):raise RuntimeError('Published layout mapping differs from live seats')
        if data.get('layout_type')=='image':
            picture=client.get(layout.json()['image_url']);picture.raise_for_status()
            with Image.open(BytesIO(picture.content)) as image:image.verify()
        result.update(unique_users=len(seen),distinct_sessions=100,distinct_seats=len(assignments),capacity=sum(s['capacity'] for s in seats.values()),queue_enabled=listing.json()['queue_policy']['enabled'],layout_type=layout.json().get('type','grid'))
        if master:
            client.cookies.clear();home=client.get('/');home.raise_for_status()
            pre=client.cookies.get('labseat_pre_csrf')
            if not pre:raise RuntimeError('Missing normal login CSRF cookie')
            login=client.post('/auth/login',json={'username':scope.username(0),'password':scope.password(master,0)},headers={'X-CSRF-Token':pre})
            login.raise_for_status()
            csrf=login.json()['csrf_token']
            logout=client.post('/auth/logout',json={},headers={'X-CSRF-Token':csrf});logout.raise_for_status()
            result['normal_password_login_logout']='PASS'
        identity=identities[0]
        client.cookies.clear();client.cookies.set('labseat_session',identity['session_token']);client.cookies.set('labseat_csrf',identity['csrf_token'])
        client.headers['X-CSRF-Token']=identity['csrf_token']
        try:
            joined=client.post(f'/lab-sessions/{scope.lab}/queue/join',json={});joined.raise_for_status()
            if joined.json()['status'] not in ('ADMITTED','DISABLED'):raise RuntimeError('Smoke was not admitted')
            held=client.post('/holds',json={'session_id':str(scope.lab),'seat_id':identity['seat_id']});held.raise_for_status();rid=held.json()['hold_id']
            confirmed=client.post(f'/holds/{rid}/confirm',json={});confirmed.raise_for_status();rid=confirmed.json()['reservation_id']
            if confirmed.json()['status']!='CONFIRMED':raise RuntimeError('Confirmation failed')
            qr=client.get(f'/me/tickets/{rid}/qr');qr.raise_for_status()
            with Image.open(BytesIO(qr.content)) as image:image.verify()
            result['hold_confirm_qr']='PASS'
        finally:
            if rid:
                cancelled=client.post(f'/reservations/{rid}/cancel',json={});cancelled.raise_for_status()
                if cancelled.json()['status']!='CANCELLED':raise RuntimeError('Smoke reservation was not cancelled')
                private(output/'smoke-receipt.json',{'reservation_id':rid,'session_id':str(scope.lab)})
            left=client.post(f'/lab-sessions/{scope.lab}/queue/leave',json={});left.raise_for_status()
    with Session() as db:
        for _ in range(45):
            db.expire_all();job=db.scalar(select(EmailJob).where(EmailJob.reservation_id==UUID(rid)))
            delivery=db.get(NotificationDelivery,(UUID(rid),'ReservationConfirmed'))
            if job and job.status=='SKIPPED' and delivery and delivery.status=='SKIPPED':break
            time.sleep(2)
        if not job or job.status!='SKIPPED' or job.attempts!=0 or job.provider_message_id or not delivery or delivery.status!='SKIPPED':raise RuntimeError('Synthetic email was not verified SKIPPED')
        result['email']={'job':'SKIPPED','delivery':'SKIPPED','provider_attempts':0}
    result['cancel_queue_leave']='PASS'
    result['sessions_expire_at']=data['sessions_expire_at']
    result['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    result['verified']=True
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=('prepare','sessions','verify','cleanup','smoke','physics-map','mechanic-map'))
    p.add_argument('--batch',required=True);p.add_argument('--backup',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--close-at')
    p.add_argument('--minimum-valid-seconds',type=int,default=14400)
    p.add_argument('--manifest-id');p.add_argument('--execute',action='store_true');p.add_argument('--local-verify',action='store_true')
    args=p.parse_args();scope=Scope(args.batch)
    private_root=Path(os.getenv('ASSESSMENT_PRIVATE_OUTPUT_ROOT',str(Path(__file__).resolve().parents[3]/'.local/assessment'))).resolve()
    if not args.output.resolve().is_relative_to(private_root):raise ValueError('Load credentials must remain in the private output root')
    backup=json.loads(args.backup.read_text());backup['_directory']=str(args.backup.parent)
    if not backup.get('verified') or not backup.get('assets_verified') or not backup['restore_verification']['verified']:
        raise ValueError('A verified database-and-image backup is required first')
    if args.minimum_valid_seconds<3600 or args.minimum_valid_seconds>28500:raise ValueError('Invalid minimum session TTL')
    if args.stage=='cleanup' and args.manifest_id!=str(scope.id('manifest')):raise ValueError('Cleanup requires the exact scope manifest ID')
    if args.stage in ('prepare','sessions','smoke','physics-map','mechanic-map') and not args.execute:
        print(json.dumps({'plan_only':True,'batch':scope.name,'stage':args.stage,'users':100,'events':1,'schedules':1}));return
    master_path=args.output/'load-master.txt';args.output.mkdir(parents=True,exist_ok=True)
    master=master_path.read_text().strip() if master_path.exists() else None
    result=None;tokens=None
    with Session.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':scope.id('lock').int%(2**63-1)})
        proof=verify_demo(db,backup,args.local_verify)
        if args.stage=='prepare':
            if master is None:
                if db.scalar(select(User.id).where(User.id.in_(scope.users)).limit(1)):
                    raise RuntimeError('Existing fixture requires its original private master; do not replace credentials')
                master=secrets.token_urlsafe(48)
                with os.fdopen(os.open(master_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:stream.write(master)
            if not args.close_at:raise ValueError('An explicit timezone-aware close time is required')
            prepare(db,scope,master,datetime.fromisoformat(args.close_at.replace('Z','+00:00')))
            result=manifest(db,scope)
        elif args.stage=='sessions':result,tokens=sessions(db,scope,args.minimum_valid_seconds)
        elif args.stage=='physics-map':result=physics_map(db,scope,args.output)
        elif args.stage=='mechanic-map':result=mechanic_map(db,scope,args.output)
        elif args.stage=='cleanup':result=cleanup(db,scope,args.execute)
        elif args.stage=='smoke':result=smoke(scope,args.output,args.minimum_valid_seconds,master)
        else:result=manifest(db,scope)
        result['demo_unchanged']=verify_demo(db,backup,args.local_verify)
    if args.stage=='sessions':private(args.output/'synthetic-sessions.json',tokens)
    if args.stage=='sessions' or (args.stage=='prepare' and not (args.output/'manifest.json').exists()):private(args.output/'manifest.json',result)
    if args.stage in ('physics-map','mechanic-map'):
        with Session() as db:updated=manifest(db,scope)
        updated['sessions_status']='REISSUE_REQUIRED_AFTER_MAP_CHANGE'
        private(args.output/'manifest.json',updated)
    if args.stage=='prepare':private(args.output/'accounts.json',[{'username':scope.username(i),'role':'student','password':scope.password(master,i)} for i in range(100)])
    private(args.output/(args.stage+'-result.json'),result)
    print(json.dumps({'stage':args.stage,'batch':scope.name,'manifest_id':str(scope.id('manifest')),'execute':args.execute,'demo_unchanged':True,'capacity':result.get('capacity'),'sessions':len(tokens) if tokens else None,'counts':result.get('before')}),flush=True)


if __name__=='__main__':main()
