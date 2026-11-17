"""auth HTTP API."""
from fastapi import Request, Response
from sqlalchemy import select
from app.models import LoginSession
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from app.schemas import LoginInput, RegisterInput
import app.modules.profiles.service as profiles
from fastapi import APIRouter
from app.shared.http import DB

router = APIRouter()

def pre_auth_csrf(request):
    pre=request.cookies.get('labseat_pre_csrf','')
    svc.require(bool(pre) and auth.secrets.compare_digest(pre,request.headers.get('x-csrf-token','')),403,'csrf','CSRF token không hợp lệ')


def discard_previous_session(db,request):
    old=request.cookies.get('labseat_session')
    if old:
        session=db.scalar(select(LoginSession).where(LoginSession.token_hash==auth.digest(old)))
        if session:db.delete(session)


@router.post('/auth/login')
def login(data: LoginInput, request: Request, response: Response, db=DB):
    pre_auth_csrf(request)
    from app.modules.accounts.service import throttle
    throttle('login:ip',request.client.host if request.client else 'unknown',50,900)
    result=auth.login(db,data.username,data.password,response)
    discard_previous_session(db,request)
    return result


@router.post('/auth/register',status_code=201)
def register(data: RegisterInput, request: Request, response: Response, db=DB):
    pre_auth_csrf(request)
    result=auth.register(db,data.username,data.password,response)
    discard_previous_session(db,request)
    return result


@router.post('/auth/logout')
def logout(request: Request, response: Response, db=DB):
    _, session = auth.authenticate(db, request, write=True)
    db.delete(session)
    response.delete_cookie('labseat_session')
    response.delete_cookie('labseat_csrf')
    return {'status':'logged_out'}


@router.get('/me')
def me(request: Request, db=DB):
    user, _ = auth.authenticate(db, request)
    return {'id':user.id, 'username':user.username, 'role':user.role, 'profile_complete':profiles.complete(user),'full_name':user.full_name,'avatar_url':profiles.avatar_url(user),'email_verified':bool(user.email_verified_at),'account_status':user.status}


