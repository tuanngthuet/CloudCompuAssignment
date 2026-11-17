"""Durable email intents, provider idempotency and authenticated delivery evidence."""

from datetime import timedelta, datetime, timezone
import base64
import hashlib
import hmac
import json
import os
import uuid
from html import escape
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.infrastructure.database.session import Session
from app.models import (
    EmailJob,
    PlatformEvent,
    User,
    Reservation,
    AuthChallenge,
    EmailSuppression,
    WebhookInbox,
    Event,
    LabSession,
)
from app.modules.booking.service import require, now
from app.shared.http import DB
from app.modules.auth import service as auth
from .content import ticket_details, EmailTicket, render_confirmation, qr_png
from .brevo import EmailProviderError

from app.infrastructure.observability.metrics import emit

router = APIRouter()
TERMINAL = {
    "ACCEPTED",
    "DELIVERED",
    "DEFERRED",
    "SOFT_BOUNCE",
    "SKIPPED",
    "UNKNOWN",
    "HARD_BOUNCE",
    "BLOCKED",
    "COMPLAINT",
    "FAILED",
}


def enqueue(
    db, user_id, kind, recipient, reservation_id=None, context=None, job_id=None
):
    job = EmailJob(
        id=job_id or uuid.uuid4(),
        user_id=user_id,
        kind=kind,
        recipient=recipient.strip().lower(),
        reservation_id=reservation_id,
        context=context or {},
    )
    if kind in ("ticket", "resend") and reservation_id:
        detail = ticket_details(db, db.get(Reservation, reservation_id))
        job.context = {
            **job.context,
            "ticket": {
                "id": str(detail.id),
                "ticket_code": detail.ticket_code,
                "event_name": detail.event_name,
                "room_name": detail.room_name,
                "seat_code": detail.seat_code,
                "start_at": detail.start_at.isoformat(),
                "end_at": detail.end_at.isoformat(),
                "session_kind": detail.session_kind,
            },
        }
    db.add(job)
    db.flush()
    db.add(PlatformEvent(kind="email", subject_id=job.id))
    return job


def ticket_from_context(context):
    value = dict(context["ticket"])
    value["id"] = uuid.UUID(value["id"])
    for key in ("start_at", "end_at"):
        value[key] = datetime.fromisoformat(value[key])
    return EmailTicket(**value)


def content(db, job):
    base = os.getenv("EMAIL_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    if job.kind in ("ticket", "resend"):
        detail = ticket_from_context(job.context)
        return {
            "subject": "LABSEAT — Xác nhận đăng kí thành công",
            "html": render_confirmation(
                detail, base, os.getenv("EMAIL_SUPPORT_EMAIL", "")
            ),
            "qr": qr_png(detail.ticket_code),
        }
    heading = {
        "verify": "Xác minh email LABSEAT",
        "reset": "Đặt lại mật khẩu LABSEAT",
        "email_changed": "Email tài khoản đã thay đổi",
        "cancelled": "Thông báo hủy ca",
        "anonymization": "Thông báo thời hạn lưu tài khoản",
    }.get(job.kind)
    require(heading is not None, 422, "invalid_job", "Loại email không hợp lệ.")
    text = "Thông tin tài khoản LABSEAT của bạn đã được cập nhật."
    link = ""
    if job.kind in ("verify", "reset"):
        c = db.get(AuthChallenge, uuid.UUID(job.context["challenge_id"]))
        if not c or c.consumed_at or now(db) >= c.expires_at:
            return None
        link = f"{base}/#auth-action?purpose={c.purpose}&id={c.id}&token=__LABSEAT_AUTH_TOKEN__"
        text = "Mở liên kết và bấm xác nhận. Liên kết chỉ sử dụng một lần."
    elif job.kind == "cancelled":
        text = (
            "Ca "
            + job.context.get("name", "")
            + " đã bị hủy. "
            + job.context.get("reason", "")
        )
    elif job.kind == "anonymization":
        text = "Tài khoản không hoạt động sẽ được ẩn danh sau ít nhất30 ngày. Đăng nhập để tiếp tục sử dụng và giữ dữ liệu."
    body = (
        '<html lang="vi"><body style="margin:0;background:#f4f4f4;font-family:Arial,sans-serif"><table role="presentation" style="max-width:640px;width:100%;margin:24px auto;background:white"><tr><td style="padding:24px;border-bottom:4px solid #24365a"><img alt="LABSEAT" width="150" src="'
        + escape(base)
        + '/static/labseat-email.png"></td></tr><tr><td style="padding:28px"><h1 style="font-size:24px">'
        + escape(heading)
        + "</h1><p>"
        + escape(text)
        + "</p>"
    )
    if link:
        body += (
            '<p><a href="'
            + escape(link, quote=True)
            + '">'
            + escape(heading)
            + "</a></p>"
        )
    body += '</td></tr><tr><td style="padding:24px;background:#24365a;color:white">LABSEAT · Hệ thống đăng kí ca thi và thực hành<br>Email tự động, vui lòng không trả lời.</td></tr></table></body></html>'
    return {"subject": "LABSEAT — " + heading, "html": body}


def dispatch(job_id, email, session_factory=Session):
    # Commit claim BEFORE I/O; a process crash leaves durable ambiguity, not a new send intent.
    with session_factory.begin() as db:
        job = db.scalar(select(EmailJob).where(EmailJob.id == job_id).with_for_update())
        if job is None:
            return
        if job.status in TERMINAL:
            return
        clock = now(db)
        if (
            job.status == "SENDING"
            and job.last_attempt_at
            and clock - job.last_attempt_at < timedelta(seconds=30)
        ):
            raise EmailProviderError("Email job is already in progress")
        if job.send_started_at and clock - job.send_started_at >= timedelta(minutes=29):
            job.status = "UNKNOWN"
            job.last_error = "acceptance_unknown"
            emit("EmailUnknown")
            return
        user = db.get(User, job.user_id)
        invalid = (
            user is None
            or user.status != "ACTIVE"
            or not email
            or not job.recipient
            or db.get(EmailSuppression, job.recipient) is not None
        )
        if job.kind in ("ticket", "resend", "anonymization", "cancelled"):
            invalid |= (
                user.status != "ACTIVE"
                or not user.email_verified_at
                or user.email != job.recipient
            )
        if job.reservation_id and job.kind in ("ticket", "resend"):
            r = db.get(Reservation, job.reservation_id)
            lab = db.get(LabSession, r.session_id)
            event = db.get(Event, lab.event_id) if lab.event_id else None
            invalid |= r.status not in ("CONFIRMED", "CHECKED_IN") or (
                event is not None and event.status != "ACTIVE"
            )
        auth_token = None
        if job.kind in ("verify", "reset"):
            from app.modules.accounts.service import challenge_token

            challenge = db.get(AuthChallenge, uuid.UUID(job.context["challenge_id"]))
            if challenge:
                candidate = challenge_token(challenge)
                if (
                    challenge.consumed_at is None
                    and clock < challenge.expires_at
                    and challenge.email_version == user.email_version
                    and hmac.compare_digest(
                        hashlib.sha256(candidate.encode()).hexdigest(),
                        challenge.token_hash,
                    )
                ):
                    auth_token = candidate
            invalid |= auth_token is None
        frozen = job.context.get("_rendered")
        if invalid:
            message = None
        elif frozen:
            message = dict(frozen)
            if message.get("qr"):
                message["qr"] = base64.b64decode(message["qr"])
        else:
            message = content(db, job)
            if message:
                if getattr(email, "settings", None):
                    message["sender"] = {
                        "name": email.settings.sender_name,
                        "email": email.settings.sender_email,
                    }
                snapshot = dict(message)
                if snapshot.get("qr"):
                    snapshot["qr"] = base64.b64encode(snapshot["qr"]).decode("ascii")
                job.context = {**job.context, "_rendered": snapshot}
        if message is None:
            job.status = "SKIPPED"
            job.completed_at = clock
            return
        if auth_token:
            # Snapshot contains a placeholder; never persist a bearer auth token.
            message = dict(message)
            message["html"] = message["html"].replace(
                "__LABSEAT_AUTH_TOKEN__", auth_token
            )
        job.status = "SENDING"
        job.send_started_at = job.send_started_at or clock
        job.last_attempt_at = clock
        job.attempts += 1
        recipient = job.recipient
        context = job.context
        emit("EmailAttempt")
    try:
        if hasattr(email, "send_message"):
            provider_id = email.send_message(recipient, message, job_id)
        else:
            provider_id = email.send(recipient, ticket_from_context(context))
    except EmailProviderError as exc:
        with session_factory.begin() as db:
            job = db.scalar(
                select(EmailJob).where(EmailJob.id == job_id).with_for_update()
            )
            if job.status in ("SENDING", "PENDING"):
                job.status = "UNKNOWN" if "duplicate" in str(exc) else "PENDING"
                job.last_error = (
                    "provider_duplicate"
                    if job.status == "UNKNOWN"
                    else "provider_failure"
                )
        raise
    except Exception:
        with session_factory.begin() as db:
            job = db.scalar(
                select(EmailJob).where(EmailJob.id == job_id).with_for_update()
            )
            if job.status in ("SENDING", "PENDING"):
                job.status = "PENDING"
                job.last_error = "provider_failure"
        raise
    with session_factory.begin() as db:
        job = db.scalar(select(EmailJob).where(EmailJob.id == job_id).with_for_update())
        job.provider_message_id = provider_id
        if job.status in ("SENDING", "PENDING", "UNKNOWN"):
            job.status = "ACCEPTED"
        job.completed_at = now(db)
        emit("EmailAccepted")


def publish_platform(queue, session_factory=Session):
    for _ in range(10):
        with session_factory.begin() as db:
            event = db.scalar(
                select(PlatformEvent)
                .where(PlatformEvent.published_at.is_(None))
                .order_by(
                    __import__("sqlalchemy").case(
                        (PlatformEvent.kind == "email", 0), else_=1
                    ),
                    PlatformEvent.created_at,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not event:
                return
            if event.kind == "email":
                queue.publish(
                    json.dumps({"type": "email_job", "job_id": str(event.subject_id)})
                )
            else:
                from app.realtime import publish

                publish(event.subject_id)
            event.published_at = now(db)


def receive_webhook(db, payload):
    values = payload if isinstance(payload, list) else [payload]
    require(len(values) <= 100, 422, "invalid_input", "Webhook quá lớn.")
    for value in values:
        require(isinstance(value, dict), 422, "invalid_input", "Webhook không hợp lệ.")
        message_id = str(value.get("message-id", ""))
        event = str(value.get("event", "")).lower()
        require(
            0 < len(message_id) <= 254 and len(event) <= 30,
            422,
            "invalid_input",
            "Webhook không hợp lệ.",
        )
        try:
            stamp = float(value.get("ts_event", value.get("ts", 0)))
            occurred = datetime.fromtimestamp(stamp, timezone.utc)
            require(
                stamp > 0 and occurred <= now(db) + timedelta(minutes=10),
                422,
                "invalid_input",
                "Thời điểm webhook không hợp lệ.",
            )
        except (ValueError, TypeError, OverflowError):
            require(False, 422, "invalid_input", "Webhook không hợp lệ.")
        custom = value.get("X-Mailin-custom", "")
        job = None
        try:
            job = db.get(EmailJob, uuid.UUID(str(custom)))
        except (ValueError, TypeError):
            pass
        if job is None:
            job = db.scalar(
                select(EmailJob)
                .where(EmailJob.provider_message_id == message_id)
                .limit(1)
            )
        fingerprint = hashlib.sha256(
            json.dumps([message_id, event, stamp], separators=(",", ":")).encode()
        ).hexdigest()
        db.execute(
            insert(WebhookInbox)
            .values(
                fingerprint=fingerprint,
                job_id=job.id if job else None,
                provider_message_id=message_id,
                event=event,
                occurred_at=occurred,
            )
            .on_conflict_do_nothing()
        )


def process_webhooks(db):
    mapping = {
        "sent": "ACCEPTED",
        "request": "ACCEPTED",
        "delivered": "DELIVERED",
        "deferred": "DEFERRED",
        "soft_bounce": "SOFT_BOUNCE",
        "hard_bounce": "HARD_BOUNCE",
        "blocked": "BLOCKED",
        "spam": "COMPLAINT",
        "invalid_email": "HARD_BOUNCE",
        "error": "FAILED",
    }
    rows = list(
        db.scalars(
            select(WebhookInbox)
            .where(
                WebhookInbox.processed_at.is_(None),
                (WebhookInbox.job_id.is_not(None))
                | select(EmailJob.id)
                .where(EmailJob.provider_message_id == WebhookInbox.provider_message_id)
                .exists(),
            )
            .order_by(WebhookInbox.occurred_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        job = (
            db.scalar(
                select(EmailJob).where(EmailJob.id == row.job_id).with_for_update()
            )
            if row.job_id
            else db.scalar(
                select(EmailJob)
                .where(EmailJob.provider_message_id == row.provider_message_id)
                .with_for_update()
                .limit(1)
            )
        )
        if job is None:
            continue
        status = mapping.get(row.event)
        if status and (
            job.provider_event_at is None or row.occurred_at >= job.provider_event_at
        ):
            permanent = {"HARD_BOUNCE", "BLOCKED", "COMPLAINT"}
            if job.status not in permanent and not (
                job.status == "DELIVERED"
                and status in ("ACCEPTED", "DEFERRED", "SOFT_BOUNCE")
            ):
                job.status = status
                job.provider_event_at = row.occurred_at
                job.provider_message_id = row.provider_message_id
            if status in permanent and job.recipient:
                db.execute(
                    insert(EmailSuppression)
                    .values(email=job.recipient, reason=status)
                    .on_conflict_do_nothing()
                )
            if (
                status == "DELIVERED"
                and job.status == "DELIVERED"
                and job.kind == "anonymization"
                and job.context.get("notice_at")
            ):
                user = db.get(User, job.user_id)
                if user.anonymization_notice_at == datetime.fromisoformat(
                    job.context["notice_at"]
                ):
                    user.anonymization_notice_delivered_at = now(db)
        row.job_id = job.id
        row.processed_at = now(db)


@router.post("/webhooks/brevo", status_code=202)
async def brevo_webhook(request: Request, db=DB):
    secret = os.getenv("BREVO_WEBHOOK_TOKEN", "")
    path = os.getenv("BREVO_WEBHOOK_TOKEN_FILE", "")
    if path:
        from pathlib import Path

        require(
            not secret, 503, "configuration", "Chỉ cấu hình một nguồn webhook token."
        )
        secret = Path(path).read_text().strip()
    require(
        len(secret) >= 32
        and hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + secret
        ),
        403,
        "forbidden",
        "Webhook không hợp lệ.",
    )
    body = await request.body()
    require(len(body) <= 128 * 1024, 413, "payload_too_large", "Webhook quá lớn.")
    try:
        payload = json.loads(body)
    except ValueError:
        require(False, 422, "invalid_input", "Webhook không hợp lệ.")
    receive_webhook(db, payload)
    return {"status": "queued"}


def resend(db, request, reservation_id, admin=False):
    from app.modules.accounts.service import throttle, audit

    actor, _ = auth.authenticate(db, request, write=True, admin=admin)
    r = db.get(Reservation, reservation_id)
    require(
        r is not None and (admin or r.user_id == actor.id),
        404,
        "not_found",
        "Không có vé.",
    )
    user = db.get(User, r.user_id)
    require(
        r.status in ("CONFIRMED", "CHECKED_IN") and bool(user.email_verified_at),
        409,
        "email_verification_required",
        "Cần vé hợp lệ và email đã xác minh.",
    )
    require(
        db.get(EmailSuppression, user.email) is None,
        409,
        "email_suppressed",
        "Email đang bị chặn gửi. Sửa email hoặc liên hệ quản trị.",
    )
    throttle("resend:day", reservation_id, 3, 86400)
    throttle("resend:cooldown", reservation_id, 1, 60)
    job = enqueue(db, user.id, "resend", user.email, r.id)
    if admin:
        audit(db, actor.id, "ticket_email_resend", r.id)
    return {"status": "queued", "job_id": job.id}


@router.post("/me/tickets/{reservation_id}/email-resends", status_code=202)
def owner_resend(reservation_id: uuid.UUID, request: Request, db=DB):
    return resend(db, request, reservation_id)


@router.post("/admin/tickets/{reservation_id}/email-resends", status_code=202)
def admin_resend(reservation_id: uuid.UUID, request: Request, db=DB):
    return resend(db, request, reservation_id, True)


@router.get("/me/tickets/{reservation_id}/emails")
def email_history(reservation_id: uuid.UUID, request: Request, db=DB):
    actor, _ = auth.authenticate(db, request)
    r = db.get(Reservation, reservation_id)
    require(r is not None and r.user_id == actor.id, 404, "not_found", "Không có vé.")
    return [
        {"id": j.id, "status": j.status, "kind": j.kind, "created_at": j.created_at}
        for j in db.scalars(
            select(EmailJob)
            .where(EmailJob.reservation_id == r.id)
            .order_by(EmailJob.created_at.desc())
            .limit(50)
        )
    ]


@router.get("/admin/emails")
def admin_history(request: Request, db=DB):
    auth.authenticate(db, request, admin=True)
    return [
        {
            "id": j.id,
            "user_id": j.user_id,
            "reservation_id": j.reservation_id,
            "status": j.status,
            "kind": j.kind,
            "created_at": j.created_at,
            "last_error": j.last_error,
        }
        for j in db.scalars(
            select(EmailJob).order_by(EmailJob.created_at.desc()).limit(100)
        )
    ]
