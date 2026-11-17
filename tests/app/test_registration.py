"""Public signup, session lifecycle and concurrent username uniqueness on PostgreSQL."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest

URL = os.getenv('TEST_DATABASE_URL')
if not URL:
    pytest.skip('Disposable PostgreSQL required', allow_module_level=True)
if os.getenv('APP_ENV') != 'test' or not URL.rsplit('/', 1)[-1].endswith('_test'):
    raise RuntimeError('Use a disposable *_test database')
os.environ['DATABASE_URL'] = URL
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.infrastructure.database.session import Session
from app.models import User, LoginSession
from app.modules.auth.service import hasher, digest


@pytest.fixture(autouse=True, scope='module')
def migrate():
    command.upgrade(Config('migrations/alembic.ini'), 'head')


def payload(**changes):
    return dict(username='signup-' + uuid.uuid4().hex, password='  local-signup-password  ',
                password_confirm='  local-signup-password  ', email=uuid.uuid4().hex+'@example.test') | changes


def signup(client, data):
    client.get('/')
    return client.post('/auth/register', json=data,
                       headers={'X-CSRF-Token': client.cookies['labseat_pre_csrf']})


def test_signup_hashes_password_autologin_logout_and_login():
    data = payload()
    with TestClient(app) as client:
        response = signup(client, data)
        assert response.status_code == 201, response.text
        assert response.json()['role'] == 'student'
        assert 'password' not in response.text
        assert any('HttpOnly' in c and 'labseat_session=' in c for c in response.headers.get_list('set-cookie'))
        assert client.get('/me').json()['username'] == data['username']
        assert client.get('/admin/rooms/' + uuid.uuid4().hex + '/seats').status_code == 403
        with Session() as db:
            user = db.scalar(select(User).where(User.username == data['username']))
            assert user.password_hash != data['password']
            assert hasher.verify(user.password_hash, data['password'])
            assert db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id == user.id)) == 1
        old_token = client.cookies['labseat_session']
        assert client.post('/auth/logout', headers={'X-CSRF-Token': client.cookies['labseat_csrf']}).status_code == 200
        assert client.get('/me').status_code == 401
        with Session() as db:
            assert db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(old_token))) is None
        response = client.post('/auth/login', json={k: data[k] for k in ['username', 'password']},
                               headers={'X-CSRF-Token': client.cookies['labseat_pre_csrf']})
        assert response.status_code == 200
        assert client.get('/me').json()['username'] == data['username']


def test_duplicate_username_does_not_change_account_or_session():
    data = payload()
    with TestClient(app) as client:
        assert signup(client, data).status_code == 201
        token = client.cookies['labseat_session']
        response = signup(client, data | dict(password='another-password-123', password_confirm='another-password-123'))
        assert response.status_code == 409
        assert response.json()['code'] == 'username_taken'
        assert client.cookies['labseat_session'] == token
        assert client.get('/me').json()['username'] == data['username']
        with Session() as db:
            user = db.scalar(select(User).where(User.username == data['username']))
            assert hasher.verify(user.password_hash, data['password'])
            assert db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id == user.id)) == 1


@pytest.mark.parametrize('changes', [
    dict(username='ab'), dict(username='bad name'), dict(username='bad/name'),
    dict(username=' user'), dict(username='a' * 101),
    dict(password='', password_confirm=''),
    dict(email=''), dict(email='bad-email'), dict(email='a@b.test\nBcc:x@y.test'),
    dict(password=' ' * 12, password_confirm=' ' * 12),
    dict(password_confirm='not-the-same-password'), dict(role='admin'),
])
def test_invalid_signup_creates_no_user(changes):
    data = payload(**changes)
    with TestClient(app) as client:
        assert signup(client, data).status_code == 422
    with Session() as db:
        assert db.scalar(select(User).where(User.username == data['username'])) is None


@pytest.mark.parametrize('token', [None, 'wrong-token'])
def test_signup_requires_prelogin_csrf(token):
    data = payload()
    with TestClient(app) as client:
        client.get('/')
        response = client.post('/auth/register', json=data, headers={'X-CSRF-Token': token} if token else {})
        assert response.status_code == 403
    with Session() as db:
        assert db.scalar(select(User).where(User.username == data['username'])) is None


def test_concurrent_signup_one_account_and_one_session():
    data = payload()
    barrier = Barrier(2)
    def attempt():
        with TestClient(app) as client:
            client.get('/')
            barrier.wait(timeout=10)
            return client.post('/auth/register', json=data, headers={'X-CSRF-Token': client.cookies['labseat_pre_csrf']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409], [r.text for r in responses]
    with Session() as db:
        users = db.scalars(select(User).where(User.username == data['username'])).all()
        assert len(users) == 1
        assert db.scalar(select(func.count()).select_from(LoginSession).where(LoginSession.user_id == users[0].id)) == 1


def test_signup_replaces_previous_authenticated_session():
    with TestClient(app) as client:
        assert signup(client, payload()).status_code == 201
        previous = client.cookies['labseat_session']
        new = payload()
        assert signup(client, new).status_code == 201
        assert client.get('/me').json()['username'] == new['username']
        with Session() as db:
            assert db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(previous))) is None


@pytest.mark.parametrize('password', ['x', 'short', 'a b'])
def test_short_password_and_signup_email_are_saved_unverified(password):
    data=payload(password=password,password_confirm=password)
    data['email']='  '+data['email'].upper()+'  '
    with TestClient(app) as client:
        assert signup(client,data).status_code==201
        assert client.get('/me').json()['email_verified'] is False
        profile=client.get('/me/profile').json()
        assert profile['email']==data['email'].strip().lower()
        assert profile['pending_email'] is None
        assert profile['cccd']==''
        response=client.post('/auth/email-verification/request',headers={'X-CSRF-Token':client.cookies['labseat_csrf']})
        assert response.status_code==202,response.text
        from app.models import AuthChallenge
        from app.modules.accounts.service import challenge_token
        with Session() as db:
            user=db.scalar(select(User).where(User.username==data['username']))
            challenge=db.scalar(select(AuthChallenge).where(AuthChallenge.user_id==user.id,AuthChallenge.purpose=='verify',AuthChallenge.consumed_at.is_(None)))
            confirmation={'challenge_id':str(challenge.id),'token':challenge_token(challenge)}
        response=client.post('/auth/email-verification/confirm',json=confirmation,headers={'X-CSRF-Token':client.cookies['labseat_pre_csrf']})
        assert response.status_code==200,response.text
        assert client.get('/me').json()['email_verified'] is True


def test_registration_requires_email():
    data=payload();data.pop('email')
    with TestClient(app) as client:
        assert signup(client,data).status_code==422


def test_duplicate_normalized_email_preserves_existing_account_and_session():
    data=payload()
    with TestClient(app) as client:
        assert signup(client,data).status_code==201
        token=client.cookies['labseat_session']
        duplicate=payload(email=' '+data['email'].upper()+' ')
        response=signup(client,duplicate)
        assert response.status_code==409 and response.json()['code']=='email_taken'
        assert client.cookies['labseat_session']==token
        assert client.get('/me').json()['username']==data['username']


def test_concurrent_registration_same_email_is_atomic():
    first=payload();second=payload(email=first['email'])
    barrier=Barrier(2)
    def attempt(data):
        with TestClient(app) as client:
            client.get('/');barrier.wait(timeout=10)
            return client.post('/auth/register',json=data,headers={'X-CSRF-Token':client.cookies['labseat_pre_csrf']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(attempt,[first,second]))
    assert sorted(r.status_code for r in responses)==[201,409], [r.text for r in responses]
    assert next(r for r in responses if r.status_code==409).json()['code']=='email_taken'
