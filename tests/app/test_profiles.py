"""Private profiles and exam gates against a disposable PostgreSQL database."""
import os
import uuid
import pytest
if not os.getenv('TEST_DATABASE_URL'):pytest.skip('Disposable DB required',allow_module_level=True)
if os.getenv('APP_ENV')!='test' or not os.environ['TEST_DATABASE_URL'].endswith('_test'):raise RuntimeError('Disposable test DB only')
from test_event_management import client,payload,create
from test_db import clean_db
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.infrastructure.database.session import Session
from app.models import User,Seat,SessionSeat,Reservation,LabSession
import app.infrastructure.redis.admission as booking_queue
import app.modules.booking.service as services

VALID=dict(full_name='Nguyễn Văn An',cccd='012345678901',phone='0912345678',email='an@example.test')

@pytest.fixture
def student(client):
    with TestClient(app) as c:
        c.get('/')
        p='profile-only-password'
        assert c.post('/auth/register',json={'username':'profile-'+uuid.uuid4().hex,'password':p,'password_confirm':p},headers={'X-CSRF-Token':c.cookies['labseat_pre_csrf']}).status_code==201
        c.headers['X-CSRF-Token']=c.cookies['labseat_csrf']
        yield c


def verify_saved(student):
    from app.modules.accounts.service import issue,verify,challenge_token
    uid=student.get('/me').json()['id']
    with Session.begin() as db:
        user=db.get(User,uid)
        c=issue(db,user,'verify',user.pending_email or user.email)
        verify(db,c.id,challenge_token(c))


def ca(client,kind='exam'):
    e=create(client,payload()|{'session_type':kind}).json();s=e['schedule']
    with Session.begin() as db:
        seat=Seat(room_id=s['room_id'],seat_code='A01');db.add(seat);db.flush()
        db.add(SessionSeat(session_id=s['id'],seat_id=seat.id));sid=str(seat.id)
    return s['id'],sid


def test_profile_auth_csrf_normalization_and_private_fields(client,student):
    with TestClient(app) as guest:
        assert guest.get('/me/profile').status_code==401
        assert guest.put('/me/profile',json=VALID).status_code==401
    assert student.get('/me/profile').json()==dict(full_name='',cccd='',phone='',email='',profile_complete=False,avatar_url=None,pending_email=None,email_verified=False)
    assert student.put('/me/profile',json=VALID,headers={'X-CSRF-Token':'wrong'}).status_code==403
    data=VALID|{'full_name':'  Nguyễn   Văn An  ','phone':'+84 912 345 678','email':'an@example.test'}
    response=student.put('/me/profile',json=data);assert response.status_code==200,response.text
    result=response.json();assert result==VALID|{'email':'an@example.test','profile_complete':True,'avatar_url':None,'pending_email':VALID['email'],'email_verified':False}
    assert student.get('/me/profile').json()==result
    identity=student.get('/me').json();assert identity['profile_complete']
    assert not {'cccd','phone','email'}&identity.keys()
    assert client.get('/me/profile').json()['cccd']==''
    assert not any(v in client.get('/events').text for v in [VALID['cccd'],VALID['phone']])
    assert student.put('/me/profile',json=VALID|{'role':'admin'}).status_code==422


@pytest.mark.parametrize('changes',[{'full_name':'12345'},{'cccd':'123'},{'cccd':'１２３４５６７８９０１２'},{'phone':'abc'},{'phone':'1234567890'},{'email':'not-email'},{'email':'a@b.test\nBcc:x@y.test'}])
def test_invalid_profile_does_not_change_saved_values(student,changes):
    assert student.put('/me/profile',json=VALID).status_code==200
    assert student.put('/me/profile',json=VALID|changes).status_code==422
    assert student.get('/me/profile').json()==VALID|{'profile_complete':True,'avatar_url':None,'pending_email':VALID['email'],'email_verified':False}


@pytest.mark.parametrize('missing',['full_name','cccd'])
def test_each_required_field_blocks_exam_queue_and_hold(client,student,missing):
    session,seat=ca(client)
    assert student.put('/me/profile',json=VALID|{missing:''}).status_code==200
    response=student.post(f'/lab-sessions/{session}/queue/join',json={})
    assert response.status_code==409 and response.json()['code']=='profile_required'
    response=student.post('/holds',json={'session_id':session,'seat_id':seat})
    assert response.status_code==409 and response.json()['code']=='profile_required'
    with Session() as db:assert db.scalar(select(func.count()).select_from(Reservation).where(Reservation.session_id==session))==0
    assert student.put('/me/profile',json=VALID).json()['profile_complete']
    verify_saved(student)
    assert student.post(f'/lab-sessions/{session}/queue/join',json={}).status_code==200
    held=student.post('/holds',json={'session_id':session,'seat_id':seat});assert held.status_code==200,held.text
    assert student.post('/holds/'+held.json()['hold_id']+'/confirm').status_code==200


def test_practice_does_not_require_profile_and_existing_exam_can_be_cancelled(client,student):
    session,seat=ca(client,'practice')
    assert not student.get('/me').json()['profile_complete']
    assert student.post(f'/lab-sessions/{session}/queue/join',json={}).json()['code']=='email_verification_required'
    student.put('/me/profile',json={'email':VALID['email']})
    verify_saved(student)
    assert student.post(f'/lab-sessions/{session}/queue/join',json={}).status_code==200
    held=student.post('/holds',json={'session_id':session,'seat_id':seat});assert held.status_code==200
    assert student.post('/holds/'+held.json()['hold_id']+'/confirm').status_code==200
    session,seat=ca(client)
    student.put('/me/profile',json=VALID)
    verify_saved(student)
    held=student.post('/holds',json={'session_id':session,'seat_id':seat}).json()
    student.put('/me/profile',json={'email':VALID['email']})
    response=student.post('/holds/'+held['hold_id']+'/confirm')
    assert response.status_code==409 and response.json()['code']=='profile_required'
    assert student.post('/reservations/'+held['hold_id']+'/cancel').status_code==200


@pytest.mark.parametrize('changes', [{'email':''}, {'email':'   '}])
def test_required_email_rejects_empty_without_changing_profile(student, changes):
    assert student.put('/me/profile', json=VALID).status_code == 200
    response = student.put('/me/profile', json=VALID | changes)
    assert response.status_code == 422
    assert student.get('/me/profile').json()['email'] == VALID['email']


def test_email_cannot_be_omitted_from_profile_update(student):
    assert student.put('/me/profile', json={k:v for k,v in VALID.items() if k != 'email'}).status_code == 422


@pytest.mark.parametrize('omit_phone', [False, True])
def test_phone_is_optional_and_does_not_block_exam(client, student, omit_phone):
    values = VALID | {'phone':''}
    if omit_phone: values.pop('phone')
    response = student.put('/me/profile', json=values)
    assert response.status_code == 200 and response.json()['profile_complete']
    assert response.json()['phone'] == ''
    verify_saved(student)
    session, seat = ca(client)
    assert student.post(f'/lab-sessions/{session}/queue/join', json={}).status_code == 200
    held = student.post('/holds', json={'session_id':session, 'seat_id':seat})
    assert held.status_code == 200
    assert student.post('/holds/' + held.json()['hold_id'] + '/confirm').status_code == 200


def test_profile_without_email_blocks_exam(client, student):
    assert student.put('/me/profile', json=VALID).status_code == 200
    user_id = student.get('/me').json()['id']
    with Session.begin() as db:
        user = db.get(User, user_id)
        user.pending_email = None
        user.email = ''  # Existing data remains readable, not silently filled or reset.
    assert not student.get('/me/profile').json()['profile_complete']
    session, seat = ca(client)
    assert student.post(f'/lab-sessions/{session}/queue/join', json={}).json()['code'] == 'profile_required'
    assert student.post('/holds', json={'session_id':session,'seat_id':seat}).json()['code'] == 'profile_required'
