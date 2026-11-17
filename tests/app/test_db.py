"""Integration tests: dedicated PostgreSQL 16 database only, never production."""
import os
import pytest

URL=os.getenv('TEST_DATABASE_URL')
if not URL:
    pytest.skip('TEST_DATABASE_URL required: PostgreSQL tests not executed',allow_module_level=True)
if os.getenv('APP_ENV')!='test' or not URL.rsplit('/',1)[-1].split('?')[0].endswith('_test'):
    raise RuntimeError('Refusing destructive tests outside APP_ENV=test / *_test database')
os.environ['DATABASE_URL']=URL

from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from app.infrastructure.database.session import engine, Session
from app.models import User, Room, Seat, LabSession, SessionSeat, Reservation, AuditEvent, LoginSession
from app.modules.auth.service import hasher, digest
from app.main import app
import app.modules.booking.service as svc

@pytest.fixture(autouse=True)
def clean_db():
    assert engine.dialect.name=='postgresql'
    command.upgrade(Config('migrations/alembic.ini'),'head')
    with engine.begin() as conn:
        assert conn.scalar(text('SHOW server_version')).startswith('16.')
        conn.execute(text('UPDATE booking_queue_settings SET enabled=false,recovery_pending=false,policy_version=1,capacity=10,selection_seconds=120,heartbeat_seconds=5,waiting_grace_seconds=60,recovery_not_before=NULL'))
        conn.execute(text('TRUNCATE queue_policy_events,rate_limits,platform_events,storage_objects,email_suppressions,maintenance_states'))
        conn.execute(text('TRUNCATE audit_events,reservations,session_seats,lab_sessions,seats,rooms,login_sessions,users CASCADE'))
    yield

@pytest.fixture
def data():
    with Session.begin() as db:
        users=[User(username=f'u{i}',role='student',password_hash='unused',email=f'u{i}@example.test',email_verified_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)) for i in range(100)]
        db.add_all(users); room=Room(name='test'); db.add(room); db.flush()
        seats=[Seat(room_id=room.id,seat_code=f'A{i}') for i in range(5)];db.add_all(seats);db.flush()
        t=svc.now(db)
        lab=LabSession(checkin_enabled=True,checkin_close_mode='manual',room_id=room.id,open_at=t-timedelta(hours=1),close_at=t+timedelta(minutes=5),start_at=t+timedelta(minutes=10),end_at=t+timedelta(hours=1));db.add(lab);db.flush()
        db.add_all([SessionSeat(session_id=lab.id,seat_id=s.id) for s in seats])
        return [u.id for u in users],lab.id,[s.id for s in seats],room.id

def acquire(user,lab,seat):
    try:
        with Session.begin() as db:
            r,_=svc.hold(db,user,lab,seat)
            return r.id
    except svc.Problem as exc:
        assert exc.status==409
        return None

def assert_invariants():
    with Session() as db:
        for column in (Reservation.user_id,Reservation.seat_id):
            assert not db.execute(select(column,Reservation.session_id,func.count()).where(Reservation.status.in_(svc.ACTIVE)).group_by(column,Reservation.session_id).having(func.count()>1)).all()

def test_100_users_one_seat(data):
    users,lab,seats,_=data
    # Worker barrier starts simultaneous requests without requiring 100 DB connections.
    barrier=Barrier(20)
    with Session.begin() as db:
        for i,user in enumerate(users):
            db.add(LoginSession(user_id=user,token_hash=digest(f'test-token-{i}'),csrf_hash=digest(f'test-csrf-{i}'),expires_at=svc.now(db)+timedelta(hours=1)))
    def run(i):
        barrier.wait(timeout=30)
        with TestClient(app) as client:
            client.cookies.set('labseat_session',f'test-token-{i}')
            response=client.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])},headers={'X-CSRF-Token':f'test-csrf-{i}'})
            assert response.status_code in (200,409), response.text
            return response.status_code
    with ThreadPoolExecutor(max_workers=20) as pool:
        results=list(pool.map(run,range(100)))
    assert results.count(200)==1 and results.count(409)==99
    assert_invariants()

def test_one_user_many_seats(data):
    users,lab,seats,_=data
    with ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lambda s:acquire(users[0],lab,s),seats))
    assert sum(r is not None for r in results)==1
    assert_invariants()

def test_expiry_releases_and_forbids_confirm(data):
    users,lab,seats,_=data
    rid=acquire(users[0],lab,seats[0])
    with Session.begin() as db:
        db.get(Reservation,rid).hold_expires_at=svc.now(db)-timedelta(seconds=1)
    with pytest.raises(svc.Problem),Session.begin() as db:
        svc.transition(db,users[0],rid)
    assert acquire(users[1],lab,seats[0])
    with Session() as db:
        assert db.get(Reservation,rid).status=='EXPIRED'

def test_idempotence_and_checkin(data):
    users,lab,seats,_=data
    with Session.begin() as db: db.get(User,users[1]).role='admin'
    rid=acquire(users[0],lab,seats[0])
    with Session.begin() as db:
        r=svc.transition(db,users[0],rid); code=r.ticket_code
    with Session.begin() as db:
        assert svc.transition(db,users[0],rid).ticket_code==code
    with Session.begin() as db:
        first=svc.transition(db,users[1],action='check-in',ticket_code=code).checked_in_at
    with Session.begin() as db:
        assert svc.transition(db,users[1],action='check-in',ticket_code=code).checked_in_at==first
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent))==3
    with pytest.raises(svc.Problem),Session.begin() as db:
        svc.transition(db,users[0],rid,'cancel')

def test_cancel_repeat_and_ownership(data):
    users,lab,seats,_=data
    rid=acquire(users[0],lab,seats[0])
    with pytest.raises(svc.Problem) as exc,Session.begin() as db:
        svc.transition(db,users[1],rid)
    assert exc.value.status==404
    for _ in range(2):
        with Session.begin() as db:
            assert svc.transition(db,users[0],rid,'cancel').status=='CANCELLED'
    assert acquire(users[1],lab,seats[0])

def test_hold_repeat_no_extension_and_cap(data):
    users,lab,seats,_=data
    with Session.begin() as db:
        db.get(LabSession,lab).close_at=svc.now(db)+timedelta(seconds=30)
    rid=acquire(users[0],lab,seats[0])
    with Session() as db:
        expiry=db.get(Reservation,rid).hold_expires_at
        assert expiry==db.get(LabSession,lab).close_at
    assert acquire(users[0],lab,seats[0])==rid
    with Session() as db:
        assert db.get(Reservation,rid).hold_expires_at==expiry

def test_db_unique_backstop(data):
    users,lab,seats,_=data
    acquire(users[0],lab,seats[0])
    with pytest.raises(IntegrityError),Session.begin() as db:
        db.add(Reservation(user_id=users[1],session_id=lab,seat_id=seats[0],status='HELD',hold_expires_at=svc.now(db)+timedelta(seconds=50)))

def login_client(name,password):
    c=TestClient(app)
    assert c.get('/').status_code==200
    response=c.post('/auth/login',json={'username':name,'password':password},headers={'X-CSRF-Token':c.cookies['labseat_pre_csrf']})
    assert response.status_code==200
    c.headers['X-CSRF-Token']=c.cookies['labseat_csrf']
    return c

def test_api_auth_qr_csv_images(data,tmp_path,monkeypatch):
    from PIL import Image
    from io import BytesIO
    users,lab,seats,room=data
    password='local-test-password'
    with Session.begin() as db:
        for i,role in [(0,'student'),(1,'student'),(2,'admin')]:
            u=db.get(User,users[i]);u.password_hash=hasher.hash(password);u.role=role
    c=login_client('u0',password);other=login_client('u1',password);admin=login_client('u2',password)
    assert c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])},headers={'X-CSRF-Token':''}).status_code==403
    r=c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])});assert r.status_code==200
    rid=r.json()['hold_id']
    assert other.post(f'/holds/{rid}/confirm').status_code==404
    confirmed=c.post(f'/holds/{rid}/confirm');assert confirmed.status_code==200
    assert c.post(f'/holds/{rid}/confirm').json()['ticket_code']==confirmed.json()['ticket_code']
    assert c.get(f'/me/tickets/{rid}/qr').headers['content-type']=='image/png'
    assert other.get(f'/me/tickets/{rid}/qr').status_code==404
    assert c.post('/admin/check-ins',json={'ticket_code':confirmed.json()['ticket_code']}).status_code==403
    assert admin.post('/admin/check-ins',json={'ticket_code':confirmed.json()['ticket_code']}).status_code==200
    csv=admin.get(f'/admin/lab-sessions/{lab}/registrations.csv');assert csv.status_code==200 and csv.content.startswith(b'\xef\xbb\xbf')
    assert confirmed.json()['ticket_code'] not in csv.text
    monkeypatch.setenv('LOCAL_STORAGE_PATH',str(tmp_path))
    im=BytesIO();Image.new('RGB',(4,4)).save(im,'PNG')
    assert admin.post(f'/admin/rooms/{room}/image',files={'file':('x.png',im.getvalue(),'image/png')}).status_code==200
    assert c.get(f'/rooms/{room}/image').headers['content-type']=='image/jpeg'
    assert c.post('/auth/logout').status_code==200
    assert c.get('/me').status_code==401

def test_migration_matches_models():
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.infrastructure.database.session import Base
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn),Base.metadata)==[]

def test_confirm_rechecks_clock_after_wait(data):
    import threading
    import time
    users,lab,seats,_=data
    rid=acquire(users[0],lab,seats[0])
    with Session.begin() as db:
        db.get(Reservation,rid).hold_expires_at=svc.now(db)+timedelta(seconds=1)
    entered=threading.Event()
    def confirm():
        with pytest.raises(svc.Problem),Session.begin() as db:
            entered.set()
            svc.transition(db,users[0],rid)
    with Session.begin() as blocker:
        blocker.scalar(select(User).where(User.id==users[0]).with_for_update())
        pool=ThreadPoolExecutor(max_workers=1)
        future=pool.submit(confirm)
        assert entered.wait(5)
        time.sleep(1.2)
    future.result(timeout=20)
    pool.shutdown()
    with Session() as db:
        assert db.get(Reservation,rid).ticket_code is None

def test_confirm_cancel_race(data):
    users,lab,seats,_=data
    rid=acquire(users[0],lab,seats[0])
    def run(action):
        try:
            with Session.begin() as db:
                return svc.transition(db,users[0],rid,action).status
        except svc.Problem:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,['confirm','cancel']))
    with Session() as db:
        assert db.get(Reservation,rid).status=='CANCELLED'
    assert_invariants()

def test_admin_overlap_and_guards(data):
    users,lab,seats,room=data
    with Session.begin() as db:
        u=db.get(User,users[2]);u.role='admin';u.password_hash=hasher.hash('local-test-password')
    admin=login_client('u2','local-test-password')
    with Session() as db:
        r=db.get(LabSession,lab)
        payload={k:getattr(r,k).isoformat() for k in ['open_at','close_at','start_at','end_at']}
        payload['room_id']=str(room)
    assert admin.post('/admin/lab-sessions',json=payload).status_code==409
    acquire(users[0],lab,seats[0])
    assert admin.patch(f'/admin/lab-sessions/{lab}',json=payload).status_code==409
    assert admin.delete(f'/admin/rooms/{room}/seats/{seats[0]}').status_code==409
    assert admin.post(f'/admin/rooms/{room}/image',files={'file':('fake.png',b'bad','image/png')}).status_code==422

def test_time_boundaries(data):
    users,lab,seats,_=data
    with Session.begin() as db: db.get(User,users[1]).role='admin'
    rid=acquire(users[0],lab,seats[0])
    with Session.begin() as db:
        code=svc.transition(db,users[0],rid).ticket_code
        t=svc.now(db)
        session=db.get(LabSession,lab)
        session.open_at=t-timedelta(hours=2);session.close_at=t-timedelta(minutes=2)
        session.start_at=t-timedelta(minutes=1);session.end_at=t-timedelta(seconds=1)
    with Session.begin() as db:
        assert svc.transition(db,users[1],action='check-in',ticket_code=code).status == 'CHECKED_IN'
    with pytest.raises(svc.Problem),Session.begin() as db:
        svc.transition(db,users[0],rid,'cancel')
    with pytest.raises(svc.Problem),Session.begin() as db:
        svc.hold(db,users[1],lab,seats[1])

def test_two_process_http_and_restart(data,tmp_path):
    """Local real HTTP: shared DB sessions, tickets and image files; no AWS claim."""
    import socket
    import subprocess
    import sys
    import time
    import httpx
    from io import BytesIO
    from PIL import Image
    users,lab,seats,room=data
    with Session.begin() as db:
        for i in (0,2):
            u=db.get(User,users[i]);u.password_hash=hasher.hash('local-test-password')
        db.get(User,users[2]).role='admin'
    def port():
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));return s.getsockname()[1]
    ports=[port(),port()]; processes=[]
    env=os.environ|{'DATABASE_URL':URL,'LOCAL_STORAGE_PATH':str(tmp_path),'STORAGE_BACKEND':'local'}
    def start(p):
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(p),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        processes.append(process)
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail('HTTP app process exited')
            try:
                if httpx.get(f'http://127.0.0.1:{p}/healthz',timeout=1).status_code==200:return process
            except httpx.TransportError:pass
            time.sleep(.1)
        pytest.fail('HTTP startup timed out')
    try:
        first=start(ports[0]);start(ports[1])
        a=f'http://127.0.0.1:{ports[0]}';b=f'http://127.0.0.1:{ports[1]}'
        with httpx.Client(base_url=a) as student,httpx.Client(base_url=a) as admin:
            for client,name in [(student,'u0'),(admin,'u2')]:
                client.get('/')
                login=client.post('/auth/login',json={'username':name,'password':'local-test-password'},headers={'X-CSRF-Token':client.cookies['labseat_pre_csrf']})
                assert login.status_code==200
                client.headers['X-CSRF-Token']=client.cookies['labseat_csrf']
            hold=student.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])});assert hold.status_code==200
            rid=hold.json()['hold_id']
            confirmed=student.post(f'{b}/holds/{rid}/confirm');assert confirmed.status_code==200
            im=BytesIO();Image.new('RGB',(3,3),'red').save(im,'PNG')
            assert admin.post(f'/admin/rooms/{room}/image',files={'file':('a.png',im.getvalue(),'image/png')}).status_code==200
            assert student.get(f'{b}/rooms/{room}/image').status_code==200
            first.terminate();first.wait(timeout=10);start(ports[0])
            assert student.get('/me').status_code==200
            assert student.get('/me/tickets').json()[0]['ticket_code']==confirmed.json()['ticket_code']
            assert student.get(f'/rooms/{room}/image').status_code==200
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait()

def test_migration_roundtrip_and_idempotent_seed():
    import subprocess
    import sys
    from sqlalchemy import inspect
    config=Config('migrations/alembic.ini')
    command.downgrade(config,'base')
    assert 'reservations' not in inspect(engine).get_table_names()
    command.upgrade(config,'head')
    env=os.environ|{'SEED_PASSWORD':'local-test-only-password','APP_ENV':'test','DATABASE_URL':URL}
    for _ in range(2):
        subprocess.run([sys.executable,'-m','app.cli','seed','--students','100'],env=env,check=True,capture_output=True,timeout=60)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(User))==101
        assert db.scalar(select(func.count()).select_from(Room))==1
        assert db.scalar(select(func.count()).select_from(Seat))==60
        assert db.scalar(select(func.count()).select_from(LabSession))==2
        assert db.scalar(select(func.count()).select_from(SessionSeat))==120

def test_map_save_revision_and_freeze(data):
    from app.layouts import read,save
    from app.schemas import MapInput
    users,lab,seats,room=data
    with Session.begin() as db:
        original=read(db,room)
        payload={k:v for k,v in original.items() if k!='locked'}
        payload['columns']=12
        saved=save(db,room,MapInput(**payload))
        assert saved['revision']==1
    with pytest.raises(svc.Problem) as exc,Session.begin() as db:
        save(db,room,MapInput(**payload))
    assert exc.value.status==409
    acquire(users[0],lab,seats[0])
    with Session() as db:
        assert read(db,room)['locked'] is True
    payload['revision']=1
    with pytest.raises(svc.Problem) as exc,Session.begin() as db:
        save(db,room,MapInput(**payload))
    assert exc.value.status==409

def test_new_room_default_map_and_registration_guards(data):
    users,lab,seats,room=data
    with Session.begin() as db:
        u=db.get(User,users[2]);u.role='admin';u.password_hash=hasher.hash('local-test-password')
    c=login_client('u2','local-test-password')
    created=c.post('/admin/rooms',json={'name':'Editor default'})
    assert created.status_code==201
    rid=created.json()['id'];layout=c.get(f'/rooms/{rid}/seat-map').json()
    assert len([e for e in layout['elements'] if e['kind']=='seat'])==60
    assert layout['revision']==1
    acquire(users[0],lab,seats[0])
    assert c.post(f'/admin/rooms/{room}/seats',json={'seat_code':'Z99'}).status_code==409
    assert c.delete(f'/admin/rooms/{room}/seats/{seats[1]}').status_code==409

def test_map_add_delete_syncs_session_seats(data):
    from app.layouts import read,save
    from app.schemas import MapInput
    import uuid
    users,lab,seats,room=data
    with Session.begin() as db:
        payload=read(db,room);payload.pop('locked')
        removed=next(e for e in payload['elements'] if e.get('seat_id')==str(seats[0]))
        payload['elements'].remove(removed)
        payload['elements'].append(dict(id=str(uuid.uuid4()),kind='seat',seat_code='NEW',x=7,y=11,width=1,height=1))
        result=save(db,room,MapInput(**payload))
        new=next(e for e in result['elements'] if e.get('seat_code')=='NEW')
        assert db.get(Seat,seats[0]) is None
        assert db.scalar(select(SessionSeat.id).where(SessionSeat.session_id==lab,SessionSeat.seat_id==uuid.UUID(new['seat_id'])))
        assert db.scalar(select(func.count()).select_from(SessionSeat).where(SessionSeat.session_id==lab))==5

# Admission integration cases use the isolated PostgreSQL fixture.
@pytest.fixture
def queue_store():
    import uuid
    from urllib.parse import urlsplit
    import app.infrastructure.redis.admission as q
    if not os.getenv('TEST_REDIS_URL'):
        pytest.skip('TEST_REDIS_URL (isolated Redis database 15) required')
    assert urlsplit(os.environ['TEST_REDIS_URL']).path == '/15'
    assert os.getenv('REDIS_URL') == os.environ['TEST_REDIS_URL']
    q.client.cache_clear()
    with Session.begin() as db:
        row=db.get(__import__('app.models',fromlist=['QueueSettings']).QueueSettings,1)
        row.enabled=True;row.epoch=uuid.uuid4()
        db.flush();policy=q.policy(db)
    store=q.RedisQueue();store.prepare(policy)
    yield store,policy
    keys=list(store.connection.scan_iter(f'labseat:queue:{{{policy.epoch}:*'))
    if keys:store.connection.delete(*keys)
    store.connection.close();store.connection.connection_pool.disconnect();q.client.cache_clear()


def queue_call(store,policy,lab,user,operation='join',generation=None):
    import secrets
    with Session() as db:
        row=db.get(LabSession,lab)
        return store.call(operation,policy,lab,user,row.close_at,row.end_at,generation or secrets.token_hex(16))


def authenticated_client(user):
    import secrets
    token=secrets.token_hex(24);csrf=secrets.token_hex(24)
    with Session.begin() as db:
        db.add(LoginSession(user_id=user,token_hash=digest(token),csrf_hash=digest(csrf),expires_at=svc.now(db)+timedelta(hours=1)))
    c=TestClient(app);c.cookies.set('labseat_session',token);c.cookies.set('labseat_csrf',csrf);c.headers['X-CSRF-Token']=csrf
    return c


def test_queue_fifo_capacity_and_concurrent_join(data,queue_store):
    users,lab,_,_=data;store,p=queue_store
    with ThreadPoolExecutor(max_workers=20) as pool:
        results=list(pool.map(lambda user:queue_call(store,p,lab,user),users))
    assert sum(r['status']=='ADMITTED' for r in results)==10
    assert sum(r['status']=='WAITING' for r in results)==90
    keys=store.keys(p,lab)
    assert store.connection.zcard(keys[3])==10
    assert store.connection.hlen(keys[4])==100
    first_waiting=store.connection.zrange(keys[2],0,0)[0]
    admitted=next(user for user,result in zip(users,results) if result['status']=='ADMITTED')
    queue_call(store,p,lab,admitted,'leave')
    assert queue_call(store,p,lab,first_waiting,'guard')['status']=='ADMITTED'
    assert store.connection.zcard(keys[3])==10
    assert store.connection.zcard(keys[2])==89


def test_queue_reload_deadline_and_multi_tab(data,queue_store):
    users,lab,_,_=data;store,p=queue_store
    first=queue_call(store,p,lab,users[0])
    repeated=queue_call(store,p,lab,users[0])
    heartbeat=queue_call(store,p,lab,users[0],'heartbeat')
    assert first['generation']==repeated['generation']==heartbeat['generation']
    assert first['expires_ms']==repeated['expires_ms']==heartbeat['expires_ms']
    assert store.connection.zcard(store.keys(p,lab)[3])==1


def test_queue_waiter_expiry_and_explicit_rejoin(data,queue_store):
    import json
    users,lab,_,_=data;store,p=queue_store
    for user in users[:11]:queue_call(store,p,lab,user)
    keys=store.keys(p,lab);user=str(users[10])
    old=json.loads(store.connection.hget(keys[4],user))
    now_ms=queue_call(store,p,lab,users[0],'guard')['server_ms']
    store.connection.zadd(keys[5],{user:now_ms-(p.waiting_grace_seconds+1)*1000})
    assert queue_call(store,p,lab,user,'heartbeat')['status']=='EXPIRED'
    new=queue_call(store,p,lab,user)
    assert new['status']=='WAITING' and new['generation']!=old['generation']


def test_queue_admission_expiry_does_not_renew(data,queue_store):
    import json
    users,lab,_,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0]);keys=store.keys(p,lab);user=str(users[0])
    entry=json.loads(store.connection.hget(keys[4],user));entry['expires']=1
    store.connection.hset(keys[4],user,json.dumps(entry));store.connection.zadd(keys[3],{user:1})
    assert queue_call(store,p,lab,user,'heartbeat')['status']=='EXPIRED'
    c=authenticated_client(users[0])
    r=c.post('/holds',json={'session_id':str(lab),'seat_id':str(data[2][0])})
    assert r.status_code==409 and r.json()['code']=='queue_expired'
    assert c.post(f'/lab-sessions/{lab}/queue/heartbeat',json={}).json()['admission_expires_at'] is None


def test_queue_sessions_are_independent_and_close_caps_lease(data,queue_store):
    users,lab,_,_=data;store,p=queue_store
    for user in users[:11]:queue_call(store,p,lab,user)
    with Session.begin() as db:
        room=Room(name='other room');db.add(room);db.flush();t=svc.now(db)
        other=LabSession(room_id=room.id,open_at=t-timedelta(minutes=1),close_at=t+timedelta(seconds=10),start_at=t+timedelta(minutes=1),end_at=t+timedelta(hours=1))
        db.add(other);db.flush();other_id=other.id;close_ms=other.close_at.timestamp()*1000
    result=queue_call(store,p,other_id,users[10])
    assert result['status']=='ADMITTED' and result['expires_ms']<=close_ms
    with Session.begin() as db:db.get(LabSession,other_id).close_at=svc.now(db)-timedelta(seconds=1)
    c=authenticated_client(users[10])
    assert c.post(f'/lab-sessions/{other_id}/queue/join',json={}).json()['code']=='registration_closed'
    assert c.post(f'/lab-sessions/{other_id}/queue/heartbeat',json={}).json()['status']=='CLOSED'


def test_queue_api_auth_csrf_and_backend_bypass(data,queue_store):
    users,lab,seats,_=data
    c=TestClient(app)
    assert c.post(f'/lab-sessions/{lab}/queue/join',json={}).status_code==401
    c=authenticated_client(users[0])
    assert c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])}).json()['code']=='queue_waiting'
    c.headers['X-CSRF-Token']='wrong'
    assert c.post(f'/lab-sessions/{lab}/queue/join',json={}).status_code==403
    c.headers['X-CSRF-Token']=c.cookies['labseat_csrf']
    assert c.post(f'/lab-sessions/{lab}/queue/join',json={'user_id':str(users[1])}).status_code==422
    response=c.post(f'/lab-sessions/{lab}/queue/join',json={})
    assert response.status_code==200 and response.json()['status']=='ADMITTED'
    assert set(response.json())=={'session_id','status','number_ahead','admission_expires_at','server_time','heartbeat_after_seconds','epoch','policy_version'}
    assert c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])}).status_code==200
    assert c.post(f'/lab-sessions/{lab}/queue/join',json={}).json()['code']=='active_registration'


def test_queue_database_rollback_does_not_consume(data,queue_store):
    users,lab,seats,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0])
    with pytest.raises(RuntimeError),Session.begin() as db:
        svc.hold(db,users[0],lab,seats[0]);raise RuntimeError('forced rollback')
    assert queue_call(store,p,lab,users[0],'guard')['status']=='ADMITTED'
    with Session() as db:assert db.scalar(select(func.count()).select_from(Reservation))==0


def test_queue_post_commit_release_failure_preserves_hold_and_retry(data,queue_store,monkeypatch):
    import app.infrastructure.redis.admission as q
    users,lab,seats,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0]);original=q.RedisQueue.call
    def fail_release(self,action,*args,**kwargs):
        if action=='consume':raise q.unavailable()
        return original(self,action,*args,**kwargs)
    monkeypatch.setattr(q.RedisQueue,'call',fail_release)
    c=authenticated_client(users[0]);payload={'session_id':str(lab),'seat_id':str(seats[0])}
    r=c.post('/holds',json=payload);assert r.status_code==200
    hold_id=r.json()['hold_id']
    assert queue_call(store,p,lab,users[0],'guard')['status']=='ADMITTED'
    monkeypatch.setattr(q.RedisQueue,'call',lambda *a,**kw: (_ for _ in ()).throw(q.unavailable()))
    assert c.post('/holds',json=payload).json()['hold_id']==hold_id
    confirmed=c.post(f'/holds/{hold_id}/confirm');assert confirmed.status_code==200
    assert c.get('/me/tickets').status_code==200
    assert c.post(f'/reservations/{hold_id}/cancel').status_code==200
    other=authenticated_client(users[1])
    assert other.post('/holds',json=payload).status_code==503


def test_queue_old_consume_cannot_remove_new_generation(data,queue_store):
    users,lab,_,_=data;store,p=queue_store
    old=queue_call(store,p,lab,users[0]);queue_call(store,p,lab,users[0],'leave')
    new=queue_call(store,p,lab,users[0]);assert old['generation']!=new['generation']
    queue_call(store,p,lab,users[0],'consume',old['generation'])
    assert queue_call(store,p,lab,users[0],'guard')['generation']==new['generation']


def test_queue_noscript_and_restart_marker_fail_closed(data,queue_store):
    import json
    users,lab,_,_=data;store,p=queue_store
    store.connection.script_flush()
    assert queue_call(store,p,lab,users[0])['status']=='ADMITTED'
    marker=json.loads(store.connection.get('labseat:queue:ready'));marker['run_id']='previous-process'
    store.connection.set('labseat:queue:ready',json.dumps(marker))
    with pytest.raises(svc.Problem) as error:queue_call(store,p,lab,users[0],'guard')
    assert error.value.status==503
    assert TestClient(app).get('/healthz').status_code==200
    assert TestClient(app).get('/readyz/queue').status_code==503


def test_queue_partial_entry_fails_closed(data,queue_store):
    users,lab,_,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0]);keys=store.keys(p,lab)
    # A simulated partial allocation must never become an uncounted valid admission.
    store.connection.zrem(keys[3],str(users[0]))
    with pytest.raises(svc.Problem) as error:queue_call(store,p,lab,users[0],'guard')
    assert error.value.status==503
    assert store.connection.hlen(keys[4])==1


def test_queue_off_does_not_construct_redis_client(data,monkeypatch):
    import app.infrastructure.redis.admission as q
    users,lab,seats,_=data
    monkeypatch.setattr(q,'client',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Redis must not be used')))
    c=authenticated_client(users[0])
    assert c.get('/lab-sessions').json()['queue_policy']['enabled'] is False
    assert c.get('/readyz/queue').json()['status']=='disabled'
    assert c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])}).status_code==200


def test_queue_operator_recovery_and_audit(data,queue_store):
    from app.queue_admin import change
    from app.models import QueueSettings,QueuePolicyEvent
    users,lab,_,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0])
    with pytest.raises(svc.Problem):change('disable','tester','must drain first')
    result=change('begin','tester','test recovery');assert result['recovery_pending'] is True
    with pytest.raises(svc.Problem):change('finish','tester','too early')
    with Session.begin() as db:db.get(QueueSettings,1).recovery_not_before=svc.now(db)-timedelta(seconds=1)
    result=change('finish','tester','drained under exclusive policy lock')
    assert result['epoch']!=str(p.epoch) and result['enabled'] is True and result['recovery_pending'] is False
    c=authenticated_client(users[0])
    assert c.post(f'/lab-sessions/{lab}/queue/heartbeat',json={}).json()['status']=='NONE'
    with Session() as db:assert db.scalar(select(func.count()).select_from(QueuePolicyEvent))==2


def test_queue_shared_between_api_processes(data,queue_store):
    import socket,subprocess,sys,time,httpx
    users,lab,seats,_=data
    with Session.begin() as db:db.get(User,users[0]).password_hash=hasher.hash('local-cross-role-password')
    processes=[]
    def start(role,port=None):
        if port is None:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        env=os.environ|{'DB_POOL_SIZE':'3'}
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        processes.append(proc)
        for _ in range(100):
            assert proc.poll() is None
            try:
                r=httpx.get(f'http://127.0.0.1:{port}/healthz',timeout=1)
                if r.status_code==200:
                    assert r.json()['deployment']=='labseat'
                    return proc,port
            except httpx.TransportError:pass
            time.sleep(.05)
        pytest.fail('App process did not start')
    try:
        _,a=start('node-a');book,b=start('node-b');base=f'http://127.0.0.1:{b}'
        with httpx.Client(base_url=f'http://127.0.0.1:{a}') as c:
            c.get('/');login=c.post('/auth/login',json={'username':'u0','password':'local-cross-role-password'},headers={'X-CSRF-Token':c.cookies['labseat_pre_csrf']});assert login.status_code==200
            c.headers['X-CSRF-Token']=c.cookies['labseat_csrf']
            first=c.post(f'/lab-sessions/{lab}/queue/join',json={});assert first.status_code==200
            state=c.post(f'{base}/lab-sessions/{lab}/queue/heartbeat',json={});assert state.status_code==200
            assert state.json()['admission_expires_at']==first.json()['admission_expires_at']
            book.terminate();book.wait(timeout=10);start('node-b',b)
            again=c.post(f'{base}/lab-sessions/{lab}/queue/heartbeat',json={});assert again.status_code==200
            assert again.json()['admission_expires_at']==first.json()['admission_expires_at']
            held=c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])});assert held.status_code==200
            assert c.post(f'{base}/holds/{held.json()["hold_id"]}/confirm').status_code==200
            assert c.get('/me/tickets').json()[0]['status']=='CONFIRMED'
            from PIL import Image
            from io import BytesIO
            image=BytesIO();Image.new('RGB',(50,50),'blue').save(image,'PNG')
            assert c.post('/me/avatar',files={'file':('avatar.png',image.getvalue(),'image/png')}).status_code==200
            assert c.get('/me/avatar').content==c.get(f'{base}/me/avatar').content
            assert c.get('/readyz/queue').status_code==c.get(f'{base}/readyz/queue').status_code==200

    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()


def test_queue_actual_redis_restart_is_fail_closed(data,queue_store):
    import subprocess,json
    from urllib.parse import urlsplit
    from app.models import QueueSettings
    from app.queue_admin import change
    container=os.getenv('TEST_REDIS_RESTART_CONTAINER')
    if not container:
        pytest.skip('Explicit disposable Redis container required for actual restart test')
    assert container.startswith('labseat-test-')
    metadata=json.loads(subprocess.check_output(['docker','inspect',container],text=True))[0]
    addresses={n['IPAddress'] for n in metadata['NetworkSettings']['Networks'].values()}
    assert urlsplit(os.environ['TEST_REDIS_URL']).hostname in addresses
    users,lab,seats,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0]);queue_call(store,p,lab,users[1])
    c=authenticated_client(users[0]);d=authenticated_client(users[1])
    hold=c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])});assert hold.status_code==200
    previous_run=store.connection.info('server')['run_id']
    subprocess.run(['docker','restart',container],check=True,capture_output=True,timeout=30)
    # docker restart may return before Redis accepts TCP connections. Test marker
    # invalidation against an ONLINE new process, rather than mere connection refusal.
    import time
    from redis.exceptions import ConnectionError,TimeoutError
    deadline=time.monotonic()+10
    while True:
        try:
            assert store.connection.info('server')['run_id']!=previous_run
            break
        except (ConnectionError,TimeoutError):
            if time.monotonic()>=deadline:raise
            time.sleep(.05)
    assert c.get('/healthz').status_code==200 and c.get('/readyz').status_code==200
    assert c.get('/readyz/queue').status_code==503
    assert d.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[1])}).status_code==503
    assert c.post(f'/holds/{hold.json()["hold_id"]}/confirm').status_code==200
    assert c.get('/me/tickets').json()[0]['status']=='CONFIRMED'
    change('begin','tester','actual disposable Redis restart')
    # Expedited TEST fixture only: this does not measure the operational 120-second drain window.
    with Session.begin() as db:db.get(QueueSettings,1).recovery_not_before=svc.now(db)-timedelta(seconds=1)
    change('finish','tester','test drain timer advanced; exclusive DB policy lock drains guards')
    assert c.get('/readyz/queue').status_code==200
    assert d.post(f'/lab-sessions/{lab}/queue/heartbeat',json={}).json()['status']=='NONE'


def test_queue_noeviction_oom_keeps_committed_ticket(data,queue_store):
    import subprocess,json
    from urllib.parse import urlsplit
    container=os.getenv('TEST_REDIS_RESTART_CONTAINER')
    if not container:pytest.skip('Explicit disposable Redis container required for global memory fixture')
    assert container.startswith('labseat-test-')
    metadata=json.loads(subprocess.check_output(['docker','inspect',container],text=True))[0]
    assert urlsplit(os.environ['TEST_REDIS_URL']).hostname in {n['IPAddress'] for n in metadata['NetworkSettings']['Networks'].values()}
    users,lab,seats,_=data;store,p=queue_store
    queue_call(store,p,lab,users[0]);c=authenticated_client(users[0]);other=authenticated_client(users[1])
    held=c.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])});assert held.status_code==200
    limit=store.connection.config_get('maxmemory')['maxmemory']
    try:
        store.connection.config_set('maxmemory',1)
        result=other.post(f'/lab-sessions/{lab}/queue/join',json={})
        assert result.status_code==503 and result.json()['code']=='queue_unavailable'
        assert c.post(f'/holds/{held.json()["hold_id"]}/confirm').status_code==200
    finally:
        store.connection.config_set('maxmemory',limit)
