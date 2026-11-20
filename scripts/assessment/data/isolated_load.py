"""Separate, backup-gated load fixture. Defaults to plan-only; never edits demo rows."""
import argparse
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
    seats=list(db.scalars(select(Seat).where(Seat.room_id==scope.room)))
    if any(s.id not in scope.seats or s.capacity!=1 for s in seats):raise RuntimeError('Seat ownership/capacity mismatch')
    if complete and {s.id for s in seats}!=set(scope.seats):raise RuntimeError('Load capacity is incomplete')


def prepare(db,scope,master,close_at):
    owned(db,scope)
    clock=now(db)
    if close_at.tzinfo is None or close_at<clock+timedelta(hours=4):raise ValueError('Load window must cover at least four hours')
    for i,uid in enumerate(scope.users):
        if not db.get(User,uid):
            db.add(User(id=uid,username=scope.username(i),role='student',
                password_hash=auth.hasher.hash(scope.password(master,i)),
                full_name=f'Tài khoản tải {i+1:03}',cccd=f'98{uid.int%10**10:010}',
                email=scope.username(i)+'@example.invalid',email_verified_at=clock))
    if not db.get(Room,scope.room):db.add(Room(id=scope.room,name='['+scope.name+'] Phòng chịu tải riêng'))
    if not db.get(Event,scope.event):db.add(Event(id=scope.event,name='Ca chịu tải riêng 21–22/11/2026 (không dùng demo)',
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
    return {'batch':scope.name,'manifest_id':str(scope.id('manifest')),'event_id':str(scope.event),
        'load_session':str(scope.lab),'room_id':str(scope.room),'users':[{'id':str(uid),'username':scope.username(i),'role':'student'} for i,uid in enumerate(scope.users)],
        'seats':[{'seat_id':str(uid),'code':f'L{i+1:03}','capacity':1} for i,uid in enumerate(scope.seats)],
        'capacity':120,'open_at':lab.open_at.isoformat(),'close_at':lab.close_at.isoformat(),
        'start_at':lab.start_at.isoformat(),'end_at':lab.end_at.isoformat(),'checkin_enabled':False}


def sessions(db,scope,minimum):
    data=manifest(db,scope);lab=db.get(LabSession,scope.lab);clock=now(db)
    if not lab.open_at<=clock or lab.close_at<clock+timedelta(seconds=minimum) or lab.start_at<=clock+timedelta(seconds=minimum):
        raise RuntimeError('Load schedule no longer covers the measurement window')
    if db.get(Event,scope.event).status!='ACTIVE':raise RuntimeError('Load event is not active')
    occupied=dict(db.execute(select(Reservation.seat_id,func.count()).where(Reservation.session_id==scope.lab,
        or_(Reservation.status.in_(('CONFIRMED','CHECKED_IN')),(Reservation.status=='HELD')&(Reservation.hold_expires_at>clock))).group_by(Reservation.seat_id)).all())
    result=[];expires=[]
    for i,uid in enumerate(scope.users):
        user=db.get(User,uid);seat=scope.seats[i]
        if user.status!='ACTIVE' or not user.email_verified_at or user.pending_email or occupied.get(seat,0):raise RuntimeError('Load user/seat is unavailable')
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
        'seat_id':str(scope.seats[i]),'seat_code':f'L{i+1:03}'} for i,uid in enumerate(scope.users)]
    return data,result


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
    if len(identities)!=100 or any(len({item[key] for item in identities})!=100 for key in ('session_token','csrf_token','seat_id')):
        raise RuntimeError('Require 100 distinct user sessions, CSRF tokens and assigned seats')
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
        if set(seats)!=set(map(str,scope.seats)) or any(seats[str(sid)]['capacity']!=1 for sid in scope.seats):raise RuntimeError('Seat mapping/capacity mismatch')
        seen=set()
        for i,identity in enumerate(identities):
            client.cookies.clear();client.cookies.set('labseat_session',identity['session_token'])
            me=client.get('/me');me.raise_for_status();user=me.json()
            if user['id']!=str(scope.users[i]) or user['role']!='student' or user['account_status']!='ACTIVE' or not user['email_verified'] or user['id'] in seen:raise RuntimeError('Live user identity mismatch')
            if not seats[identity['seat_id']]['available']:raise RuntimeError('An assigned seat is unavailable')
            seen.add(user['id'])
        result.update(unique_users=len(seen),distinct_sessions=100,distinct_seats=100,capacity=120,queue_enabled=listing.json()['queue_policy']['enabled'])
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
    p.add_argument('stage',choices=('prepare','sessions','verify','cleanup','smoke'))
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
    if args.stage in ('prepare','sessions','smoke') and not args.execute:
        print(json.dumps({'plan_only':True,'batch':scope.name,'users':100,'events':1,'schedules':1,'seats':120,'capacity':120}));return
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
        elif args.stage=='cleanup':result=cleanup(db,scope,args.execute)
        elif args.stage=='smoke':result=smoke(scope,args.output,args.minimum_valid_seconds,master)
        else:result=manifest(db,scope)
        result['demo_unchanged']=verify_demo(db,backup,args.local_verify)
    if args.stage=='sessions':private(args.output/'synthetic-sessions.json',tokens)
    if args.stage=='sessions' or (args.stage=='prepare' and not (args.output/'manifest.json').exists()):private(args.output/'manifest.json',result)
    if args.stage=='prepare':private(args.output/'accounts.json',[{'username':scope.username(i),'role':'student','password':scope.password(master,i)} for i in range(100)])
    private(args.output/(args.stage+'-result.json'),result)
    print(json.dumps({'stage':args.stage,'batch':scope.name,'manifest_id':str(scope.id('manifest')),'execute':args.execute,'demo_unchanged':True,'capacity':result.get('capacity'),'sessions':len(tokens) if tokens else None,'counts':result.get('before')}),flush=True)


if __name__=='__main__':main()
