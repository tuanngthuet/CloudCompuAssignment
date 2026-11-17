"""Event-owned schedule and layout creation without room/session admin forms."""
import os
import uuid
from datetime import datetime,timedelta,timezone
import pytest
URL=os.getenv('TEST_DATABASE_URL')
if not URL:pytest.skip('Disposable PostgreSQL required',allow_module_level=True)
if os.getenv('APP_ENV')!='test' or not URL.rsplit('/',1)[-1].endswith('_test'):raise RuntimeError('Use a disposable *_test database')
os.environ['DATABASE_URL']=URL
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import Session
from app.models import User,LoginSession,Room,Seat,RoomLayout,LabSession,SessionSeat,Reservation,Event
from app.modules.auth.service import digest
import app.modules.booking.service as svc

@pytest.fixture
def client():
    command.upgrade(Config('migrations/alembic.ini'),'head')
    token=uuid.uuid4().hex
    with Session.begin() as db:
        user=User(username='event-admin-'+token,role='admin',password_hash='unused');db.add(user);db.flush()
        db.add(LoginSession(user_id=user.id,token_hash=digest(token),csrf_hash=digest(token),expires_at=svc.now(db)+timedelta(hours=1)))
    with TestClient(app) as c:
        c.cookies.set('labseat_session',token);c.headers['X-CSRF-Token']=token
        yield c


def payload():
    now=datetime.now(timezone.utc)
    return dict(name='Event '+uuid.uuid4().hex[:8],venue='Studio',session_type='exam',schedule={k:(now+timedelta(minutes=m)).isoformat() for k,m in [('open_at',-60),('close_at',30),('start_at',60),('end_at',120)]})


def test_create_and_edit_event_owns_one_schedule_and_empty_layout(client):
    data=payload();response=create(client,data);assert response.status_code==201,response.text
    created=response.json();schedule=created['schedule'];eid=created['id']
    assert schedule['checkin_enabled'] is False
    with Session() as db:
        assert db.get(Room,uuid.UUID(schedule['room_id'])).name==data['name']
        assert db.get(RoomLayout,uuid.UUID(schedule['room_id'])).layout['elements']==[]
        assert db.scalar(select(func.count()).select_from(Seat).where(Seat.room_id==schedule['room_id']))==0
    response=update(client,eid,{**data,'name':'Renamed'})
    assert response.status_code==200,response.text
    assert response.json()['schedule']['id']==schedule['id']
    assert response.json()['schedule']['room_id']==schedule['room_id']
    with Session() as db:assert db.scalar(select(func.count()).select_from(LabSession).where(LabSession.event_id==eid))==1
    metadata={k:v for k,v in data.items() if k!='schedule'}
    response=update(client,eid,metadata)
    assert response.json()['schedule']['start_at']==created['schedule']['start_at']
    public=next(e for e in client.get('/events').json() if e['id']==eid)
    assert public['schedule']['id']==schedule['id']


def test_bad_schedule_creates_no_partial_event(client):
    data=payload();data['schedule']['end_at']=data['schedule']['start_at']
    assert create(client,data).status_code==422
    with Session() as db:assert db.scalar(select(Event).where(Event.name==data['name'])) is None


def test_cannot_change_schedule_after_ticket_and_rolls_back_metadata(client):
    data=payload();event=create(client,data).json();schedule=event['schedule']
    with Session.begin() as db:
        user=User(username=uuid.uuid4().hex,role='student',password_hash='unused');seat=Seat(room_id=schedule['room_id'],seat_code='A01');db.add_all([user,seat]);db.flush()
        db.add(SessionSeat(session_id=schedule['id'],seat_id=seat.id));db.flush()
        db.add(Reservation(session_id=schedule['id'],seat_id=seat.id,user_id=user.id,status='HELD',hold_expires_at=svc.now(db)+timedelta(minutes=3)))
    changed={**data,'name':'Should roll back','schedule':{**data['schedule'],'end_at':(datetime.fromisoformat(data['schedule']['end_at'])+timedelta(hours=1)).isoformat()}}
    response=update(client,event['id'],changed)
    assert response.status_code==409,response.text
    assert next(e for e in client.get('/events').json() if e['id']==event['id'])['name']==data['name']
    assert update(client,event['id'],data).status_code==200


def test_my_tickets_include_current_event_name_without_catalogue_requests(client):
    data=payload();event=create(client,data).json();schedule=event['schedule']
    token=uuid.uuid4().hex
    with Session.begin() as db:
        user=User(username='ticket-'+token,role='student',password_hash='unused')
        seat=Seat(room_id=schedule['room_id'],seat_code='Zone A',capacity=10)
        db.add_all([user,seat]);db.flush()
        db.add(SessionSeat(session_id=schedule['id'],seat_id=seat.id));db.flush()
        db.add(Reservation(session_id=schedule['id'],seat_id=seat.id,user_id=user.id,status='CONFIRMED',ticket_code='TICKET-CODE-'+token,hold_expires_at=svc.now(db)))
        db.add(LoginSession(user_id=user.id,token_hash=digest(token),csrf_hash=digest(token),expires_at=svc.now(db)+timedelta(hours=1)))
    metadata={k:v for k,v in data.items() if k!='schedule'};metadata['name']='Tên sự kiện đã cập nhật'
    assert update(client,event['id'],metadata).status_code==200
    with TestClient(app) as customer:
        customer.cookies.set('labseat_session',token)
        response=customer.get('/me/tickets');assert response.status_code==200,response.text
        ticket=response.json()[0]
        assert ticket['event_name']=='Tên sự kiện đã cập nhật'
        assert ticket['seat_code']=='Zone A'
        assert ticket['start_at']==event['schedule']['start_at']
        assert ticket['ticket_code']=='TICKET-CODE-'+token
        assert customer.get(f'/me/tickets/{ticket["reservation_id"]}/qr').status_code==200


def poster(size=(1280,720)):
    from io import BytesIO
    from PIL import Image
    out=BytesIO();Image.new('RGB',size,'orange').save(out,'PNG');return out.getvalue()


def create(client,data):
    import json
    return client.post('/admin/events',data={'data':json.dumps(data)},files={'poster':('ca.png',poster(),'image/png')})


def update(client,eid,data):
    import json
    return client.patch('/admin/events/'+eid,data={'data':json.dumps(data)})
