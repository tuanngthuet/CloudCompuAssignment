"""B1/B2 integration checks; an explicitly disposable PostgreSQL/Redis is required."""
import importlib.util
import json
import os
from pathlib import Path
import uuid
import socket
import subprocess
import sys
import time
from datetime import datetime,timedelta,timezone
from io import BytesIO

import pytest

if (os.getenv('APP_ENV')!='test' or not os.getenv('TEST_DATABASE_URL','').endswith('_test')
        or os.getenv('DATABASE_URL')!=os.getenv('TEST_DATABASE_URL')):
    pytest.skip('Explicit disposable DB required',allow_module_level=True)

from PIL import Image
from sqlalchemy import func,select
from app import assessment_seed as seed
from app.infrastructure.database.session import Session
from app.models import Event,LabSession,LoginSession,Reservation,Room,RoomLayout,User


@pytest.fixture(scope='module')
def dataset():
    batch=seed.Batch('tool-check-20261121')
    with Session.begin() as db:
        seed.assert_owned(db,batch)
        seed.add_users(db,batch,'disposable-test-master-only-20261121',seed.booking.now(db))
        seed.add_catalogue(db,batch,seed.booking.now(db))
    seed.book(batch)
    return batch


def art(width,height):
    blob=BytesIO();Image.new('RGB',(width,height),'white').save(blob,'PNG');return blob.getvalue()


def test_counts_hashes_and_idempotency(dataset):
    b=dataset
    with Session.begin() as db:
        users=list(db.scalars(select(User).where(User.id.in_(b.user_ids))))
        assert len(users)==508 and len({u.cccd for u in users})==508
        assert sum(u.role=='student' for u in users)==500
        assert sum(u.role=='admin' for u in users)==2 and sum(u.role=='staff' for u in users)==6
        assert all(u.email_verified_at for u in users)
        assert seed.auth.hasher.verify(users[0].password_hash,seed.password('disposable-test-master-only-20261121',users[0].username))
        seed.add_users(db,b,'disposable-test-master-only-20261121',seed.booking.now(db))
        seed.add_catalogue(db,b,seed.booking.now(db))
        assert db.scalar(select(func.count()).select_from(Event).where(Event.id.in_(b.event_ids)))==12
        assert db.scalar(select(func.count()).select_from(LabSession).where(LabSession.id.in_(b.lab_ids)))==24
    seed.book(b)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Reservation).where(Reservation.session_id.in_(b.lab_ids)))==300
    other=seed.Batch('load-check-20261121')
    assert not set(b.user_ids+b.event_ids+b.lab_ids)&set(other.user_ids+other.event_ids+other.lab_ids)


def test_renamed_custom_catalogue_and_sessions(dataset,tmp_path):
    b=dataset;poster=art(554,554)
    steps=[(seed.apply_hsa,art(2048,1137)),(seed.apply_ielts,art(1080,834)),
           (seed.apply_tsa,art(1500,947)),(seed.apply_sat,art(1200,760)),
           (seed.apply_hsa05,art(2048,1041)),(seed.apply_toeic,art(1200,760)),
           (seed.apply_bio,art(659,405)),(seed.apply_com,art(2324,1582)),
           (seed.apply_elec,art(725,466)),(seed.apply_mechanic,art(1183,1083)),
           (seed.apply_physics,art(1491,1055)),(seed.apply_chemistry,art(1491,1055))]
    with Session.begin() as db:
        for fn,image in steps:fn(db,b,image,poster)
        seed.apply_hsa05_map(db,b,art(1813,2560),house_a=True)
        seed.apply_bio_map(db,b,art(1084,1451))
        for i,e in enumerate(db.scalars(select(Event).where(Event.id.in_(b.event_ids)))):e.name=f'Ca tiếng Việt {i}'
        for i,r in enumerate(db.scalars(select(Room))):r.name=f'Phòng tùy chỉnh {i}'
    with Session.begin() as db:
        seed.assert_owned(db,b)
        revisions={r.room_id:r.revision for r in db.scalars(select(RoomLayout))}
        seed.add_catalogue(db,b,seed.booking.now(db))
        for fn,image in steps:
            if fn not in (seed.apply_hsa05,seed.apply_bio):fn(db,b,image,poster)
        seed.apply_hsa05_map(db,b,art(1813,2560),house_a=True)
        seed.apply_bio_map(db,b,art(1084,1451))
        assert revisions=={r.room_id:r.revision for r in db.scalars(select(RoomLayout))}
        _,sessions,manifest=seed.create_sessions(db,b,tmp_path,minimum_valid_seconds=14400)
        assert len(sessions)==len({s['session_token'] for s in sessions})==100
        assert len({s['csrf_token'] for s in sessions})==100
        fixtures=list(db.scalars(select(LoginSession).where(LoginSession.user_id.in_(b.user_ids[300:400]))))
        assert len(fixtures)==len({s.user_id for s in fixtures})==100
        assert {s.token_hash for s in fixtures}=={seed.auth.digest(s['session_token']) for s in sessions}
        assert {s.csrf_hash for s in fixtures}=={seed.auth.digest(s['csrf_token']) for s in sessions}
        assert all(s['session_token'] not in {f.token_hash for f in fixtures} for s in sessions)
    with Session.begin() as db:
        _,sessions,manifest=seed.create_sessions(db,b,tmp_path,minimum_valid_seconds=14400)
        assert db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id.in_(b.user_ids[300:400])))==100
    out=Path(os.getenv('ASSESSMENT_TEST_HANDOFF',str(tmp_path)))
    seed.save_private(out/'manifest.json',manifest);seed.save_private(out/'synthetic-sessions.json',sessions)
    import psycopg
    sql='\n'.join(line for line in Path(__file__).with_name('verify-batch.sql').read_text().splitlines()
                  if not line.lstrip().startswith('--'))
    for key,values in {'user_ids':b.user_ids,'event_ids':b.event_ids,'room_ids':manifest['rooms']}.items():
        sql=sql.replace(":'"+key+"'","'"+','.join(map(str,values))+"'")
    tables=[]
    with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')) as conn:
        with conn.cursor() as cur:
            for query in sql.split(';'):
                if query.strip():
                    cur.execute(query)
                    if cur.description:tables.append(cur.fetchall())
    assert dict(tables[0])=={'student':500,'admin':2,'staff':6}
    assert set(tables[1])=={('exam',6,12),('practice',6,12)}
    assert tables[2]==[(12,4,42)]
    assert sum(row[1] for row in tables[3])==300
    invariant_rows=[]
    invariant_sql='\n'.join(line for line in Path('scripts/tests/db-invariants.sql').read_text().splitlines()
                            if not line.lstrip().startswith('--'))
    with psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')) as conn:
        with conn.cursor() as cur:
            for query in invariant_sql.split(';'):
                if query.strip():
                    cur.execute(query)
                    if cur.description:invariant_rows.append(len(cur.fetchall()))
    assert invariant_rows==[0]*7
    mechanic=next(s for s in manifest['schedule_rooms'] if s['session_id']==str(b.lab_ids[18]))
    assert len(mechanic['seats'])==4 and all(s['capacity']==17 for s in mechanic['seats'])
    seed.save_private(out/'checks.json',{'users':508,'students':500,'admins':2,'staff':6,
                                       'events':12,'schedules':24,'reservations_before_smoke':300,
                                       'maps':12,'zone_range':[4,42],'mechanic_zones':4,'mechanic_capacity':17,
                                       'invariant_rows':invariant_rows,'sessions':100,'distinct_users':100,
                                       'idempotent_custom_maps':True})
    spec=importlib.util.spec_from_file_location('handoff_smoke',Path(__file__).with_name('smoke_sessions.py'))
    smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    import httpx
    try:
        for _ in range(100):
            try:
                if httpx.get(f'http://127.0.0.1:{port}/readyz').status_code==200:break
            except httpx.TransportError:pass
            time.sleep(.1)
        else:raise RuntimeError('Disposable app did not start')
        assert smoke.verify(out,f'http://127.0.0.1:{port}',14400)=={'image_maps':12,'unique_users':100,'hold_cancel':'PASS'}
    finally:server.terminate();server.wait(timeout=15)


def test_guard_rejects_identity_and_relationship_changes(dataset):
    b=dataset
    for change in ('username','type','event','room'):
        with Session() as db:
            if change=='username':db.get(User,b.user_ids[0]).username='foreign-user'
            elif change=='type':db.get(Event,b.event_ids[0]).session_type='practice'
            elif change=='event':db.get(LabSession,b.lab_ids[0]).event_id=b.event_ids[1]
            else:db.get(LabSession,b.lab_ids[0]).room_id=b.room_ids[-1]
            db.flush()
            with pytest.raises(RuntimeError):seed.assert_owned(db,b)
            db.rollback()


def test_handoff_rejects_ineligible_windows(dataset,tmp_path):
    b=dataset
    for change in ('cancelled','started','closing','pending-email','ttl'):
        with Session() as db:
            lab=db.get(LabSession,b.lab_ids[22]);clock=seed.booking.now(db)
            if change=='cancelled':db.get(Event,lab.event_id).status='CANCELLED'
            elif change=='started':
                lab.close_at=clock+timedelta(minutes=10);lab.start_at=clock+timedelta(minutes=30)
            elif change=='closing':lab.close_at=clock+timedelta(minutes=30)
            elif change=='pending-email':db.get(User,b.user_ids[300]).pending_email='pending@example.invalid'
            db.flush()
            with pytest.raises(RuntimeError):seed.create_sessions(db,b,tmp_path,minimum_valid_seconds=9*3600 if change=='ttl' else 3600)
            db.rollback()


@pytest.mark.parametrize('bad',['expired','duplicate-csrf'])
def test_smoke_rejects_bad_private_bundle_before_http(tmp_path,monkeypatch,bad):
    spec=importlib.util.spec_from_file_location('handoff_smoke',Path(__file__).with_name('smoke_sessions.py'))
    smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)
    clock=datetime.now(timezone.utc)
    sessions=[{'session_token':f'token-{i}','csrf_token':f'csrf-{i}','seat_id':'unused'} for i in range(100)]
    if bad=='duplicate-csrf':sessions[-1]['csrf_token']=sessions[0]['csrf_token']
    (tmp_path/'synthetic-sessions.json').write_text(json.dumps(sessions))
    (tmp_path/'manifest.json').write_text(json.dumps({'sessions_expire_at':(clock-timedelta(hours=1)).isoformat()}))
    monkeypatch.setattr(smoke.httpx,'Client',lambda **kwargs:pytest.fail('Invalid bundle must not make requests'))
    with pytest.raises(SystemExit):smoke.verify(tmp_path,'http://127.0.0.1:1')


def test_cleanup_refuses_foreign_reference_and_preserves_other_data(dataset):
    b=dataset
    with Session() as db:
        lab=db.get(LabSession,b.lab_ids[0]);clock=seed.booking.now(db)
        db.add(LabSession(id=uuid.uuid4(),event_id=lab.event_id,room_id=lab.room_id,
                         open_at=clock,close_at=clock+timedelta(hours=1),start_at=clock+timedelta(days=30),end_at=clock+timedelta(days=30,hours=1)))
        db.flush()
        with pytest.raises(RuntimeError,match='Non-batch schedule'):seed.cleanup(db,b)
        db.rollback()
    marker=uuid.uuid4()
    with Session.begin() as db:db.add(User(id=marker,username='foreign-preserved',password_hash='unused',role='student'))
    with Session.begin() as db:
        seed.assert_owned(db,b,cleanup=True);seed.cleanup(db,b)
    with Session.begin() as db:
        seed.cleanup(db,b)
        assert db.get(User,marker) is not None
        assert db.scalar(select(func.count()).select_from(User).where(User.id.in_(b.user_ids)))==0
        assert db.scalar(select(func.count()).select_from(Event).where(Event.id.in_(b.event_ids)))==0
        assert db.scalar(select(func.count()).select_from(LabSession).where(LabSession.id.in_(b.lab_ids)))==0
