from uuid import UUID
from datetime import timedelta
from fastapi import APIRouter, Request, Response, Query
from pydantic import Field, ConfigDict, field_validator
from sqlalchemy import select, func
from app.schemas import Input
from app.shared.http import DB, admin
from app.models import User, StaffAssignment, LabSession, EmailSuppression
from app.modules.auth import service as auth
from app.modules.auth.router import pre_auth_csrf
from app.modules.booking.service import require, now
from . import service as accounts

router = APIRouter()


class EmailRequest(Input):
    email: str = Field(min_length=1, max_length=254)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        from app.schemas import ProfileInput

        return ProfileInput.valid_email(value)


class TokenInput(Input):
    challenge_id: UUID
    token: str = Field(min_length=64, max_length=64)


class ResetInput(TokenInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    password: str = Field(min_length=12, max_length=1024)
    password_confirm: str = Field(min_length=12, max_length=1024)


class PasswordInput(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    current_password: str = Field(min_length=1, max_length=1024)
    password: str = Field(min_length=12, max_length=1024)
    password_confirm: str = Field(min_length=12, max_length=1024)


class UserUpdate(Input):
    role: str | None = None
    status: str | None = None
    reason: str = Field(min_length=1, max_length=500)


def ip(request):
    return request.client.host if request.client else "unknown"


def password_valid(user, password):
    try:
        return auth.hasher.verify(user.password_hash, password)
    except (auth.VerificationError, auth.InvalidHashError):
        return False


@router.post("/auth/email-verification/request", status_code=202)
def request_verification(request: Request, db=DB):
    user, _ = auth.authenticate(db, request, write=True)
    target = user.pending_email or user.email
    require(bool(target), 409, "profile_required", "Lưu email trong hồ sơ trước.")
    accounts.send_limits("verify", target, ip(request))
    user = db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    accounts.active(user)
    accounts.issue(db, user, "verify", user.pending_email or user.email)
    return {"status": "queued"}


@router.post("/auth/email-verification/confirm")
def confirm_verification(data: TokenInput, request: Request, db=DB):
    pre_auth_csrf(request)
    accounts.throttle("token:ip", ip(request), 30, 3600)
    return accounts.verify(db, data.challenge_id, data.token)


@router.post("/auth/password-reset/request", status_code=202)
def request_reset(data: EmailRequest, request: Request, db=DB):
    pre_auth_csrf(request)
    email = accounts.normalize_email(data.email)
    accounts.send_limits("reset", email, ip(request))
    user = db.scalar(
        select(User)
        .where(
            func.lower(func.btrim(User.email)) == email,
            User.email_verified_at.is_not(None),
            User.status == "ACTIVE",
        )
        .with_for_update()
    )
    if user:
        accounts.issue(db, user, "reset", email)
    return {
        "status": "queued",
        "message": "Nếu tài khoản hợp lệ, hướng dẫn khôi phục sẽ được gửi.",
    }


@router.post("/auth/password-reset/confirm")
def confirm_reset(data: ResetInput, request: Request, db=DB):
    pre_auth_csrf(request)
    accounts.throttle("token:ip", ip(request), 30, 3600)
    require(
        data.password == data.password_confirm and bool(data.password.strip()),
        422,
        "invalid_input",
        "Mật khẩu chưa khớp.",
    )
    user, _ = accounts.consume_challenge(db, data.challenge_id, data.token, "reset")
    user.password_hash = auth.hasher.hash(data.password)
    accounts.revoke_sessions(db, user.id)
    return {"status": "password_reset"}


@router.post("/auth/password/change")
def change_password(data: PasswordInput, request: Request, response: Response, db=DB):
    user, _ = auth.authenticate(db, request, write=True)
    accounts.throttle("change:user", user.id, 5, 3600)
    user = db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    require(
        password_valid(user, data.current_password),
        403,
        "bad_credentials",
        "Mật khẩu hiện tại không đúng.",
    )
    require(
        data.password == data.password_confirm and bool(data.password.strip()),
        422,
        "invalid_input",
        "Mật khẩu chưa khớp.",
    )
    user.password_hash = auth.hasher.hash(data.password)
    accounts.revoke_sessions(db, user.id)
    return auth.create_session(db, user, response)


@router.get("/admin/users")
def list_users(
    request: Request,
    q: str = Query(default="", max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    role: str | None = None,
    db=DB,
):
    admin_user, _ = auth.authenticate(db, request, admin=True)
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if q:
        query = query.where(
            User.username.ilike("%" + q + "%")
            | User.full_name.ilike("%" + q + "%")
            | User.email.ilike("%" + q + "%")
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "items": [
            accounts.safe_user(u)
            for u in db.scalars(
                query.order_by(User.username).offset(offset).limit(limit)
            )
        ],
        "total": total,
    }


@router.get("/admin/users/{user_id}")
def get_user(user_id: UUID, request: Request, db=DB):
    actor, _ = auth.authenticate(db, request, admin=True)
    user = db.get(User, user_id)
    require(user is not None, 404, "not_found", "Không có tài khoản.")
    accounts.audit(db, actor.id, "user_profile_view", user.id)
    return accounts.safe_user(user) | {
        "cccd": user.cccd,
        "phone": user.phone,
        "pending_email": user.pending_email,
    }


@router.patch("/admin/users/{user_id}")
def update_user(user_id: UUID, data: UserUpdate, request: Request, db=DB):
    actor = admin(db, request)
    db.execute(__import__("sqlalchemy").text("SELECT pg_advisory_xact_lock(48390372)"))
    locked = list(
        db.scalars(
            select(User)
            .where((User.id.in_([actor.id, user_id])) | (User.role == "admin"))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    actor = next(u for u in locked if u.id == actor.id)
    require(
        actor.role == "admin" and actor.status == "ACTIVE",
        403,
        "forbidden",
        "Không có quyền quản trị.",
    )
    user = next((u for u in locked if u.id == user_id), None)
    require(user is not None, 404, "not_found", "Không có tài khoản.")
    require(
        data.role is None or data.role in ("student", "staff", "admin"),
        422,
        "invalid_input",
        "Role không hợp lệ.",
    )
    require(
        data.status is None or data.status in ("ACTIVE", "LOCKED"),
        422,
        "invalid_input",
        "Trạng thái không hợp lệ.",
    )
    require(
        user.status != "ANONYMIZED", 409, "account_anonymized", "Tài khoản đã ẩn danh."
    )
    role = data.role or user.role
    status = data.status or user.status
    if (
        user.role == "admin"
        and user.status == "ACTIVE"
        and (role != "admin" or status != "ACTIVE")
    ):
        require(
            any(
                u.id != user.id and u.role == "admin" and u.status == "ACTIVE"
                for u in locked
            ),
            409,
            "last_admin",
            "Phải giữ ít nhất một admin hoạt động.",
        )
    before = {"role": user.role, "status": user.status}
    if user.role == "staff" and role != "staff":
        from sqlalchemy import delete

        db.execute(delete(StaffAssignment).where(StaffAssignment.user_id == user.id))
    user.role = role
    user.status = status
    accounts.revoke_sessions(db, user.id)
    accounts.audit(
        db,
        actor.id,
        "user_update",
        user.id,
        before=before,
        after={"role": role, "status": status},
        reason=data.reason,
    )
    return accounts.safe_user(user)


@router.put("/admin/lab-sessions/{session_id}/staff/{user_id}")
def assign_staff(session_id: UUID, user_id: UUID, request: Request, db=DB):
    actor = admin(db, request)
    list(
        db.scalars(
            select(User)
            .where(User.id.in_([actor.id, user_id]))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    accounts.active(actor)
    require(actor.role == "admin", 403, "forbidden", "Không có quyền quản trị.")
    user = db.get(User, user_id)
    require(
        user is not None and user.role == "staff" and user.status == "ACTIVE",
        409,
        "invalid_staff",
        "Chọn staff đang hoạt động.",
    )
    lab = db.scalar(
        select(LabSession).where(LabSession.id == session_id).with_for_update()
    )
    require(lab is not None, 404, "not_found", "Không có ca.")
    if db.get(StaffAssignment, (session_id, user_id)) is None:
        db.add(
            StaffAssignment(
                session_id=session_id, user_id=user_id, assigned_by=actor.id
            )
        )
        accounts.audit(db, actor.id, "staff_assign", session_id, staff_id=str(user_id))
    return {"status": "assigned"}


@router.delete("/admin/lab-sessions/{session_id}/staff/{user_id}")
def revoke_staff(session_id: UUID, user_id: UUID, request: Request, db=DB):
    actor = admin(db, request)
    list(
        db.scalars(
            select(User)
            .where(User.id.in_([actor.id, user_id]))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    accounts.active(actor)
    require(actor.role == "admin", 403, "forbidden", "Không có quyền quản trị.")
    db.scalar(select(LabSession).where(LabSession.id == session_id).with_for_update())
    row = db.get(StaffAssignment, (session_id, user_id))
    if row:
        db.delete(row)
        accounts.audit(db, actor.id, "staff_revoke", session_id, staff_id=str(user_id))
    return {"status": "revoked"}


@router.delete("/admin/email-suppressions/{email}")
def clear_suppression(email: str, request: Request, db=DB):
    actor = admin(db, request)
    row = db.get(EmailSuppression, accounts.normalize_email(email))
    if row:
        db.delete(row)
    accounts.audit(
        db,
        actor.id,
        "email_suppression_clear",
        actor.id,
        email_hash=auth.digest(accounts.normalize_email(email)),
    )
    return {"status": "cleared"}


@router.get("/admin/lab-sessions/{session_id}/staff")
def assignment_list(session_id: UUID, request: Request, db=DB):
    auth.authenticate(db, request, admin=True)
    return [
        {"id": user.id, "username": user.username, "full_name": user.full_name}
        for user in db.scalars(
            select(User)
            .join(StaffAssignment, StaffAssignment.user_id == User.id)
            .where(StaffAssignment.session_id == session_id)
            .order_by(User.username)
        )
    ]


@router.get("/admin/privacy-review")
def privacy_review(request: Request, db=DB):
    auth.authenticate(db, request, admin=True)
    clock = now(db)
    users = db.scalars(
        select(User)
        .where(
            User.role == "student",
            User.status == "ACTIVE",
            User.last_activity_at <= clock - timedelta(days=365),
            (User.anonymization_notice_delivered_at.is_(None))
            | (User.anonymization_notice_delivered_at > clock - timedelta(days=30)),
        )
        .order_by(User.last_activity_at)
        .limit(100)
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "last_activity_at": u.last_activity_at,
            "reason": "Chưa có bằng chứng giao thông báo đủ30 ngày.",
        }
        for u in users
    ]


@router.post("/admin/users/{user_id}/anonymize")
def approve_anonymization(user_id: UUID, data: UserUpdate, request: Request, db=DB):
    from app.models import Reservation

    actor = admin(db, request)
    locked = list(
        db.scalars(
            select(User)
            .where(User.id.in_([actor.id, user_id]))
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    accounts.active(actor)
    require(actor.role == "admin", 403, "forbidden", "Không có quyền quản trị.")
    user = next((u for u in locked if u.id == user_id), None)
    clock = now(db)
    require(
        user is not None
        and user.role == "student"
        and user.status == "ACTIVE"
        and user.last_activity_at <= clock - timedelta(days=365),
        409,
        "privacy_ineligible",
        "Chỉ xử lí student không hoạt động ít nhất365 ngày.",
    )
    future = db.scalar(
        select(Reservation.id)
        .join(LabSession, LabSession.id == Reservation.session_id)
        .where(
            Reservation.user_id == user_id,
            (
                (LabSession.end_at > clock)
                & Reservation.status.in_(("HELD", "CONFIRMED", "CHECKED_IN"))
            )
            | ((Reservation.status == "HELD") & (Reservation.hold_expires_at > clock)),
        )
        .limit(1)
    )
    require(
        future is None,
        409,
        "privacy_future_booking",
        "Tài khoản còn đăng kí đang hoặc sắp diễn ra.",
    )
    accounts.revoke_sessions(db, user_id)
    user.username = "anon_" + user.id.hex
    user.password_hash = "!anonymized"
    user.status = "ANONYMIZED"
    user.full_name = user.cccd = user.phone = user.email = ""
    user.pending_email = None
    user.email_verified_at = None
    user.avatar_key = None
    accounts.audit(
        db, actor.id, "privacy_manual_anonymize", user.id, reason=data.reason
    )
    return {"status": "anonymized"}
