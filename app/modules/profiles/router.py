"""profiles HTTP API."""
import uuid
from fastapi import Request, Response, UploadFile, File
from sqlalchemy import select
from app.models import User
import app.modules.auth.service as auth
import app.modules.booking.service as svc
from app.schemas import ProfileInput
from app.infrastructure.storage.objects import storage, normalize_avatar, MAX_BYTES
import app.modules.profiles.service as profiles
from fastapi import APIRouter
from app.shared.http import DB

router = APIRouter()

@router.get('/me/profile')
def my_profile(request: Request, db=DB):
    user,_=auth.authenticate(db,request)
    return profiles.output(user)


@router.put('/me/profile')
def update_profile(data: ProfileInput, request: Request, db=DB):
    user,_=auth.authenticate(db,request,write=True)
    user=db.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    from app.modules.accounts.service import normalize_email
    from app.modules.accounts.router import password_valid
    from app.modules.accounts.service import active
    active(user)
    email=normalize_email(data.email)
    if email != (user.pending_email or user.email):
        if user.email:
            svc.require(data.current_password and password_valid(user,data.current_password),403,'password_required','Nhập mật khẩu hiện tại để đổi email.')
        user.pending_email=email;user.email_version+=1
    for key,value in data.model_dump(exclude={'email','current_password'}).items():setattr(user,key,value)
    user.last_activity_at=svc.now(db);user.anonymization_notice_at=None;user.anonymization_notice_delivered_at=None
    return profiles.output(user)


@router.post('/me/avatar')
def upload_avatar(request: Request, file: UploadFile=File(...), db=DB):
    user,_=auth.authenticate(db,request,write=True)
    image=normalize_avatar(file.file.read(MAX_BYTES+1))
    user=db.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    key=f'users/{user.id}/avatars/{uuid.uuid4()}.jpg'
    adapter=storage()
    try:adapter.put(key,image)
    except Exception:raise svc.Problem(503,'storage_unavailable','Chưa lưu được ảnh đại diện.') from None
    profiles.cleanup_avatar_after_commit(db,adapter,user.avatar_key)
    from app.infrastructure.storage.registry import track
    track(db,key,True)
    user.avatar_key=key
    return profiles.output(user)


@router.get('/me/avatar')
def read_avatar(request: Request, db=DB):
    user,_=auth.authenticate(db,request)
    svc.require(bool(user.avatar_key),404,'not_found','Chưa có ảnh đại diện')
    try:image=storage().get(user.avatar_key)
    except Exception:raise svc.Problem(503,'storage_unavailable','Chưa tải được ảnh đại diện.') from None
    return Response(image,media_type='image/jpeg')


@router.delete('/me/avatar')
def remove_avatar(request: Request, db=DB):
    user,_=auth.authenticate(db,request,write=True)
    user=db.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))
    profiles.cleanup_avatar_after_commit(db,storage(),user.avatar_key)
    user.avatar_key=None
    return profiles.output(user)


