import hashlib
import os
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Request
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.models import User, LoginSession
from app.modules.booking.service import now, require
from app.errors import Problem

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def secure_cookie():
    return os.getenv('COOKIE_SECURE', 'false').lower() == 'true'

def cookie(response, name, value, httponly=True, max_age=28800):
    response.set_cookie(name, value, httponly=httponly, secure=secure_cookie(), samesite='lax', max_age=max_age, path='/')

def authenticate(db, request: Request, write=False, admin=False):
    token = request.cookies.get('labseat_session', '')
    login = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token), LoginSession.expires_at > now(db)))
    require(login is not None, 401, 'unauthenticated', 'Vui lòng đăng nhập')
    user = db.get(User, login.user_id)
    require(user is not None, 401, 'unauthenticated', 'Phiên không hợp lệ')
    from app.modules.accounts.service import active
    active(user)
    if user.last_activity_at and now(db)-user.last_activity_at > timedelta(days=1):
        db.info['active_user_id']=user.id
    if write:
        csrf = request.headers.get('x-csrf-token', '')
        require(bool(csrf) and secrets.compare_digest(login.csrf_hash, digest(csrf)), 403, 'csrf', 'CSRF token không hợp lệ')
    if admin:
        require(user.role == 'admin', 403, 'forbidden', 'Chỉ cán bộ được phép')
    return user, login

def login(db, username, password, response):
    from app.modules.accounts.service import throttle
    throttle('login:username',username,10,900)
    user = db.scalar(select(User).where(User.username == username))
    try:
        valid = hasher.verify(user.password_hash if user else DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        valid = False
    require(valid and user is not None, 401, 'bad_credentials', 'Thông tin đăng nhập không đúng')
    from app.modules.accounts.service import active
    active(user)
    user.last_activity_at=now(db);user.anonymization_notice_at=None;user.anonymization_notice_delivered_at=None
    return create_session(db, user, response)


def create_session(db, user, response):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id, token_hash=digest(token), csrf_hash=digest(csrf), expires_at=now(db) + timedelta(hours=8)))
    cookie(response, 'labseat_session', token)
    cookie(response, 'labseat_csrf', csrf, httponly=False)
    return {'id': user.id, 'username': user.username, 'role': user.role, 'csrf_token': csrf}



def register(db, username, password, email, response):
    require(db.scalar(select(User.id).where(User.username==username)) is None,
            409,'username_taken','Tên tài khoản đã tồn tại.')
    from app.modules.accounts.service import normalize_email
    email=normalize_email(email)
    require(db.scalar(select(User.id).where(func.lower(func.btrim(User.email))==email)) is None,
            409,'email_taken','Email đã được sử dụng cho tài khoản khác.')
    user=User(username=username,password_hash=hasher.hash(password),email=email,role='student')
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
    except IntegrityError as exc:
        # The unique constraint also resolves two simultaneous registrations.
        if getattr(getattr(exc.orig,'diag',None),'constraint_name',None)=='uq_users_email':
            raise Problem(409,'email_taken','Email đã được sử dụng cho tài khoản khác.') from None
        if getattr(getattr(exc.orig,'diag',None),'constraint_name',None)=='users_username_key':
            raise Problem(409,'username_taken','Tên tài khoản đã tồn tại.') from None
        raise
    return create_session(db,user,response)
