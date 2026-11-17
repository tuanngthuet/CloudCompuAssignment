"""Image map publishing, capacity races and personal tickets on disposable PostgreSQL."""
import os
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import pytest
URL=os.getenv('TEST_DATABASE_URL')
if not URL:pytest.skip('Disposable PostgreSQL required',allow_module_level=True)
if os.getenv('APP_ENV')!='test' or not URL.rsplit('/',1)[-1].endswith('_test'):raise RuntimeError('Use an isolated *_test database')
os.environ['DATABASE_URL']=URL
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image,ImageDraw
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import Session
from app.models import User,LoginSession,Room,LabSession,Seat,Reservation
from app.modules.auth.service import digest
import app.modules.booking.service as svc

@pytest.fixture
def data(tmp_path,monkeypatch):
    command.upgrade(Config('migrations/alembic.ini'),'head')
    monkeypatch.setenv('STORAGE_BACKEND','local');monkeypatch.setenv('LOCAL_STORAGE_PATH',str(tmp_path))
    suffix=uuid.uuid4().hex
    with Session.begin() as db:
        db.execute(__import__('sqlalchemy').text('UPDATE booking_queue_settings SET enabled=false,recovery_pending=false'))
        admin=User(username='admin'+suffix,password_hash='unused',role='admin')
        users=[User(username=f'u{i}{suffix}',password_hash='unused',role='student',email=f'{suffix}-{i}@example.test',email_verified_at=svc.now(db)) for i in range(20)]
        db.add_all([admin,*users]);db.flush()
        db.add(LoginSession(user_id=admin.id,token_hash=digest(suffix),csrf_hash=digest(suffix),expires_at=svc.now(db)+timedelta(hours=1)))
        ids=[u.id for u in users]
    client=TestClient(app);client.cookies.set('labseat_session',suffix);client.headers['X-CSRF-Token']=suffix
    response=client.post('/admin/rooms',json={'name':'Image map '+suffix});assert response.status_code==201,response.text
    room=response.json()['id']
    clock=__import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    lab=client.post('/admin/lab-sessions',json=dict(room_id=room,**{k:(clock+timedelta(minutes=m)).isoformat() for k,m in [('open_at',-60),('close_at',5),('start_at',10),('end_at',60)]})).json()['id']
    from test_image_detection import floorplan,encoded
    blob=encoded(floorplan())
    yield client,room,lab,ids,blob
    client.close()


def publish(data,capacity=5):
    client,room,lab,users,blob=data
    response=client.post(f'/admin/rooms/{room}/seat-map/image',files={'file':('map.png',blob,'image/png')})
    assert response.status_code==200,response.text
    draft=response.json()
    # Drop the third detected room; capacity applies to every room, no seat kind.
    configs=[dict(id=r['id'],kind='zone',label=label,capacity=cap,points=r['points']) for r,label,cap in zip(draft['regions'][:2],['Phòng A','Phòng B'],[2,capacity])]
    payload={k:draft[k] for k in ['revision','image_key','min_area']};payload['regions']=configs
    response=client.put(f'/admin/rooms/{room}/seat-map/image',json=payload)
    assert response.status_code==200,response.text
    return response.json(),payload


def test_publish_exact_mask_and_protect_geometry(data):
    client,room,lab,users,blob=data
    with TestClient(app) as guest:
        assert guest.post(f'/admin/rooms/{room}/seat-map/image',files={'file':('m.png',blob)}).status_code==401
    layout,payload=publish(data)
    assert layout['type']=='image' and len(layout['elements'])==2
    assert client.get(f'/lab-sessions/{lab}/seats').json()['layout_revision']==layout['revision']
    assert [r['capacity'] for r in layout['elements'] if r['kind']!='decoration']==[2,5]
    assert all(r['kind']=='zone' and 'points' in r for r in layout['elements'])
    assert client.get(layout['image_url']).headers['content-type']=='image/png'
    with TestClient(app) as guest:assert guest.get(layout['image_url']).status_code==200
    assert client.put(f'/admin/rooms/{room}/seat-map/image',json=payload).status_code==409
    fresh={**payload,'revision':layout['revision']}
    assert client.put(f'/admin/rooms/{room}/seat-map/image',json={**fresh,'image_key':payload['image_key'].replace(room,str(uuid.uuid4()))}).status_code==422
    bad=[dict(r) for r in payload['regions']];bad[0]['label']=bad[1]['label']
    assert client.put(f'/admin/rooms/{room}/seat-map/image',json={**fresh,'regions':bad}).status_code==422
    bad=[dict(r) for r in payload['regions']];bad[1]['capacity']=0
    assert client.put(f'/admin/rooms/{room}/seat-map/image',json={**fresh,'regions':bad}).status_code==422
    missing=[dict(r) for r in payload['regions']];missing[1].pop('capacity')
    assert client.put(f'/admin/rooms/{room}/seat-map/image',json={**fresh,'regions':missing}).status_code==422
    assert len(client.get(f'/admin/rooms/{room}/seats').json())==2



def test_add_remove_manual_rooms_and_reject_invalid_polygons(data):
    client,room,lab,users,blob=data
    layout,payload=publish(data)
    fresh=payload|{'revision':layout['revision']}
    for points in [[[-1,0],[80,0],[80,80],[0,80]],[[10,10],[80,80],[80,10],[10,80]],payload['regions'][0]['points']]:
        extra={'id':'manual','kind':'zone','label':'Phòng C','capacity':100,'points':points}
        assert client.put(f'/admin/rooms/{room}/seat-map/image',json=fresh|{'regions':[*fresh['regions'],extra]}).status_code==422
    manual={'id':'manual','label':'Phòng C','capacity':100,'points':[[350,220],[450,220],[450,300],[350,300]]}
    response=client.put(f'/admin/rooms/{room}/seat-map/image',json=fresh|{'regions':[fresh['regions'][0],manual]})
    assert response.status_code==200,response.text
    saved=response.json();assert len(saved['elements'])==2
    assert client.get(f'/lab-sessions/{lab}/seats').json()['layout_revision']==saved['revision']
    assert saved['elements'][0]['seat_id']==layout['elements'][0]['seat_id']
    assert saved['elements'][1]['capacity']==100 and saved['elements'][1]['points']==manual['points']
    reread=client.get(f'/rooms/{room}/seat-map').json()
    assert reread['detector']=='quadrilateral-v1' and reread['elements']==saved['elements']
    assert sorted(s['seat_code'] for s in client.get(f'/admin/rooms/{room}/seats').json())==['Phòng A','Phòng C']


def test_zone_capacity_races_expiry_cancel_and_personal_tickets(data):
    client,room,lab,users,blob=data
    layout,payload=publish(data,5);zone=uuid.UUID(layout['elements'][1]['seat_id']);sid=uuid.UUID(lab)
    def acquire(user):
        try:
            with Session.begin() as db:return svc.hold(db,user,sid,zone)[0].id
        except svc.Problem as error:
            assert error.status==409
            return None
    with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(acquire,users))
    held_ids=[r for r in results if r];assert len(held_ids)==5
    with Session() as db:
        rows=list(db.scalars(select(Reservation).where(Reservation.id.in_(held_ids))))
        assert {r.slot for r in rows}==set(range(5))
        owners={r.id:r.user_id for r in rows}
    available=client.get(f'/lab-sessions/{lab}/seats').json()['items']
    assert next(r for r in available if r['id']==str(zone))['remaining']==0
    with Session.begin() as db:
        confirmed=svc.transition(db,owners[held_ids[0]],held_ids[0],'confirm')
        code=confirmed.ticket_code
    assert code
    assert client.patch(f'/admin/lab-sessions/{lab}/check-in',json={'enabled':True}).status_code==200
    assert client.post('/admin/check-ins',json={'ticket_code':code}).json()['status']=='CHECKED_IN'
    with Session.begin() as db:
        svc.transition(db,owners[held_ids[1]],held_ids[1],'cancel')
        db.get(Reservation,held_ids[2]).hold_expires_at=svc.now(db)-timedelta(seconds=1)
    outsiders=[u for u,r in zip(users,results) if not r]
    assert acquire(outsiders[0]) and acquire(outsiders[1])
    assert acquire(outsiders[2]) is None
    with Session.begin() as db:
        user=owners[held_ids[0]]
        with pytest.raises(svc.Problem):svc.hold(db,user,sid,uuid.UUID(layout['elements'][0]['seat_id']))
    assert client.post(f'/admin/rooms/{room}/seat-map/image',files={'file':('m.png',blob)}).status_code==409
    assert client.put(f'/admin/rooms/{room}/seat-map/image',json={**payload,'revision':layout['revision']}).status_code==409
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Reservation).where(Reservation.session_id==sid,Reservation.status.in_(svc.ACTIVE)))==5


def test_one_account_cannot_hold_twice_across_sessions_of_one_event(data):
    from app.models import Event, SessionSeat
    client,room,lab,users,blob=data
    layout,_=publish(data,3);zone=uuid.UUID(layout['elements'][1]['seat_id'])
    with Session.begin() as db:
        event=Event(name='Single-person event',venue='Studio');db.add(event);db.flush()
        original=db.get(LabSession,uuid.UUID(lab));original.event_id=event.id
        other=LabSession(room_id=original.room_id,event_id=event.id,open_at=original.open_at,close_at=original.close_at,start_at=original.start_at,end_at=original.end_at)
        db.add(other);db.flush();db.add(SessionSeat(session_id=other.id,seat_id=zone));other_id=other.id
    with Session.begin() as db:svc.hold(db,users[0],uuid.UUID(lab),zone)
    with Session.begin() as db:
        with pytest.raises(svc.Problem) as error:svc.hold(db,users[0],other_id,zone)
        assert error.value.code=='active_registration'


def test_blank_upload_can_be_configured_with_manual_room(data):
    from test_image_detection import encoded
    client,room,lab,users,blob=data
    blank=encoded(Image.new('RGB',(200,150),'white'))
    response=client.post(f'/admin/rooms/{room}/seat-map/image',files={'file':('blank.png',blank,'image/png')})
    assert response.status_code==200,response.text
    draft=response.json();assert draft['regions']==[]
    payload={k:draft[k] for k in ['revision','image_key','min_area']}
    payload['regions']=[{'id':'manual','label':'Phòng kéo tay','capacity':30,'points':[[10,10],[180,10],[180,130],[10,130]]}]
    saved=client.put(f'/admin/rooms/{room}/seat-map/image',json=payload)
    assert saved.status_code==200,saved.text
    assert saved.json()['elements'][0]['capacity']==30
