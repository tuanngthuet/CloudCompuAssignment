"""One-use challenges, verified identity and durable distributed rate limits."""

from datetime import timedelta
import hashlib
import hmac
import os
import secrets
import uuid
from pathlib import Path
from sqlalchemy import select, delete, func, case
from sqlalchemy.dialects.postgresql import insert
from app.models import User, LoginSession, AuthChallenge, RateLimit, AdminAudit
from app.infrastructure.database.session import counter_sessions
from app.modules.booking.service import now, require


def signing_key():
    key = os.getenv("AUTH_LINK_SIGNING_KEY", "")
    path = os.getenv("AUTH_LINK_SIGNING_KEY_FILE", "")
    if key and path:
        raise ValueError("Use one auth signing key source")
    if path:
        key = Path(path).read_text().strip()
    if not key and os.getenv("APP_ENV", "local") in ("local", "test"):
        key = "labseat-local-only-auth-links-not-for-public-deployment"
    if len(key) < 32:
        raise ValueError("Configure AUTH_LINK_SIGNING_KEY with at least32 characters")
    return key.encode()


def normalize_email(value):
    return value.strip().lower()


def challenge_token(challenge):
    value = f"{challenge.id}:{challenge.purpose}:{challenge.user_id}:{challenge.email}:{challenge.email_version}:{challenge.nonce}"
    return hmac.new(signing_key(), value.encode(), hashlib.sha256).hexdigest()


def throttle(scope, identity, limit, seconds):
    # Separate transaction: a rejected login/request must not roll back its counter.
    key = hashlib.sha256((scope + ":" + str(identity)).encode()).hexdigest()
    with counter_sessions().begin() as db:
        clock = now(db)
        window = clock.replace(microsecond=0) - timedelta(
            seconds=int(clock.timestamp()) % seconds
        )
        if seconds == 60:
            window = clock
            expired = RateLimit.window_at <= clock - timedelta(seconds=60)
            values = {
                "window_at": case((expired, clock), else_=RateLimit.window_at),
                "attempts": case((expired, 1), else_=RateLimit.attempts + 1),
            }
        else:
            values = {
                "window_at": window,
                "attempts": case(
                    (RateLimit.window_at == window, RateLimit.attempts + 1), else_=1
                ),
            }
        stmt = insert(RateLimit).values(key_hash=key, window_at=window, attempts=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[RateLimit.key_hash], set_=values
        ).returning(RateLimit.attempts)
        allowed = db.scalar(stmt) <= limit
    require(
        allowed, 429, "rate_limited", "Bạn thao tác quá nhanh. Vui lòng thử lại sau."
    )


def send_limits(kind, email, ip):
    throttle(kind + ":ip", ip, 20, 3600)
    throttle(kind + ":email", normalize_email(email), 5, 3600)
    throttle(kind + ":cooldown", normalize_email(email), 1, 60)


def audit(db, actor, action, subject, **details):
    db.add(
        AdminAudit(actor_id=actor, action=action, subject_id=subject, details=details)
    )


def active(user):
    require(
        user is not None and user.status == "ACTIVE",
        403,
        "account_locked",
        "Tài khoản không hoạt động.",
    )


def eligible(db, user_id, lab):
    from app.models import Event

    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    active(user)
    event = db.get(Event, lab.event_id) if lab.event_id else None
    require(
        event is None or event.status == "ACTIVE",
        409,
        "session_inactive",
        "Ca đã hủy hoặc lưu trữ.",
    )
    if event and event.session_type == "exam":
        require(
            bool(user.full_name and (user.email or user.pending_email)),
            409,
            "profile_required",
            "Bổ sung họ tên và email để đăng kí ca thi.",
        )
    require(
        bool(user.email and user.email_verified_at),
        409,
        "email_verification_required",
        "Xác minh email để đăng kí ca.",
    )


def issue(db, user, purpose, target):
    from app.modules.notifications.jobs import enqueue

    target = normalize_email(target)
    clock = now(db)
    # Supersede only challenges of the same purpose; a reset never verifies email.
    for old in db.scalars(
        select(AuthChallenge)
        .where(
            AuthChallenge.user_id == user.id,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed_at.is_(None),
        )
        .with_for_update()
    ):
        old.consumed_at = clock
    c = AuthChallenge(
        id=uuid.uuid4(),
        user_id=user.id,
        purpose=purpose,
        email=target,
        email_version=user.email_version,
        nonce=secrets.token_hex(32),
        token_hash="",
        expires_at=clock + timedelta(hours=24)
        if purpose == "verify"
        else clock + timedelta(minutes=30),
    )
    c.token_hash = hashlib.sha256(challenge_token(c).encode()).hexdigest()
    db.add(c)
    db.flush()
    enqueue(
        db,
        user.id,
        "verify" if purpose == "verify" else "reset",
        target,
        context={"challenge_id": str(c.id)},
    )
    return c


def consume_challenge(db, challenge_id, token, purpose):
    # User before challenge follows the account mutation lock order.
    c = db.get(AuthChallenge, challenge_id)
    require(
        c is not None, 400, "invalid_token", "Liên kết không hợp lệ hoặc đã hết hạn."
    )
    user = db.scalar(
        select(User)
        .where(User.id == c.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    c = db.scalar(
        select(AuthChallenge)
        .where(AuthChallenge.id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    active(user)
    require(
        c is not None
        and c.purpose == purpose
        and c.consumed_at is None
        and now(db) < c.expires_at
        and c.email_version == user.email_version
        and secrets.compare_digest(
            c.token_hash, hashlib.sha256(token.encode()).hexdigest()
        ),
        400,
        "invalid_token",
        "Liên kết không hợp lệ hoặc đã hết hạn.",
    )
    target = (user.pending_email or user.email) if purpose == "verify" else user.email
    require(
        c.email == normalize_email(target)
        and (purpose != "reset" or user.email_verified_at is not None),
        400,
        "invalid_token",
        "Liên kết không còn hiệu lực.",
    )
    c.consumed_at = now(db)
    return user, c


def verify(db, challenge_id, token):
    from app.modules.notifications.jobs import enqueue

    user, c = consume_challenge(db, challenge_id, token, "verify")
    conflict = db.scalar(
        select(User.id).where(
            func.lower(func.btrim(User.email)) == c.email, User.id != user.id
        )
    )
    require(
        conflict is None, 409, "email_taken", "Email đã được tài khoản khác xác minh."
    )
    previous = user.email
    user.email = c.email
    user.pending_email = None
    user.email_verified_at = now(db)
    user.email_version += 1
    db.execute(
        delete(AuthChallenge).where(
            AuthChallenge.user_id == user.id, AuthChallenge.id != c.id
        )
    )
    if previous and previous != user.email:
        enqueue(db, user.id, "email_changed", previous)
    return {"status": "verified"}


def revoke_sessions(db, user_id):
    db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    for challenge in db.scalars(
        select(AuthChallenge).where(
            AuthChallenge.user_id == user_id, AuthChallenge.consumed_at.is_(None)
        )
    ):
        challenge.consumed_at = now(db)


def safe_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
        "email": user.email,
        "email_verified": bool(user.email_verified_at),
        "last_activity_at": user.last_activity_at,
    }
