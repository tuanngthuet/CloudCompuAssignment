"""Platform policy integration tests on disposable PostgreSQL; no provider I/O."""

import os
import uuid
from datetime import timedelta
import pytest

if not os.getenv("TEST_DATABASE_URL"):
    pytest.skip("Disposable PostgreSQL required", allow_module_level=True)
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from test_db import clean_db, data
from app.main import app
from app.infrastructure.database.session import Session
from app.models import (
    User,
    LoginSession,
    AuthChallenge,
    EmailJob,
    EmailSuppression,
    WebhookInbox,
    StaffAssignment,
    LabSession,
    Event,
    Reservation,
    AdminAudit,
    CheckinPolicyEvent,
    StorageObject,
)
from app.modules.auth.service import digest, hasher
from app.modules.accounts.service import (
    issue,
    verify,
    challenge_token,
    consume_challenge,
    throttle,
)
from app.modules.booking import service as booking
from app.modules.notifications.jobs import (
    enqueue,
    dispatch,
    receive_webhook,
    process_webhooks,
    resend,
)
from app.errors import Problem


def client(uid):
    token = uuid.uuid4().hex
    with Session.begin() as db:
        db.add(
            LoginSession(
                user_id=uid,
                token_hash=digest(token),
                csrf_hash=digest(token),
                expires_at=booking.now(db) + timedelta(hours=1),
            )
        )
    c = TestClient(app)
    c.get("/")
    c.cookies.set("labseat_session", token, domain="testserver.local")
    c.headers["X-CSRF-Token"] = token
    return c


def confirmed(data):
    users, lab, seats, _ = data
    with Session.begin() as db:
        r, _ = booking.hold(db, users[0], lab, seats[0])
        booking.transition(db, users[0], r.id)
        return r.id, r.ticket_code


@pytest.mark.parametrize(
    "field,value", [("email", " U0@EXAMPLE.TEST "), ("cccd", "012345678901")]
)
def test_unique_identity_database_backstop(data, field, value):
    with Session.begin() as db:
        if field == "cccd":
            db.get(User, data[0][0]).cccd = value
    with pytest.raises(IntegrityError), Session.begin() as db:
        setattr(db.get(User, data[0][1]), field, value)


def test_verification_one_use_supersedes_and_no_plaintext(data):
    uid = data[0][0]
    with Session.begin() as db:
        u = db.get(User, uid)
        u.email = ""
        u.email_verified_at = None
        u.pending_email = "NEW@example.test"
        first = issue(db, u, "verify", u.pending_email)
        old = (first.id, challenge_token(first))
        second = issue(db, u, "verify", u.pending_email)
        current = (second.id, challenge_token(second))
        assert second.token_hash != current[1]
        assert current[1] not in str(
            db.scalar(select(EmailJob.context).where(EmailJob.kind == "verify"))
        )
    with pytest.raises(Problem), Session.begin() as db:
        verify(db, *old)
    with Session.begin() as db:
        assert verify(db, *current) == {"status": "verified"}
    with Session() as db:
        u = db.get(User, uid)
        assert (
            u.email == "new@example.test"
            and u.pending_email is None
            and u.email_verified_at
        )
    with pytest.raises(Problem), Session.begin() as db:
        verify(db, *current)


@pytest.mark.parametrize("purpose", ["verify", "reset"])
def test_expired_or_wrong_purpose_link(data, purpose):
    with Session.begin() as db:
        c = issue(db, db.get(User, data[0][0]), purpose, "u0@example.test")
        key = (c.id, challenge_token(c))
        c.expires_at = booking.now(db) - timedelta(seconds=1)
    with pytest.raises(Problem), Session.begin() as db:
        consume_challenge(db, *key, purpose)


def test_unverified_blocks_hold_and_queue(data):
    c = client(data[0][0])
    with Session.begin() as db:
        db.get(User, data[0][0]).email_verified_at = None
    assert (
        c.post(
            "/holds", json={"session_id": str(data[1]), "seat_id": str(data[2][0])}
        ).json()["code"]
        == "email_verification_required"
    )
    assert (
        c.post(f"/lab-sessions/{data[1]}/queue/join", json={}).json()["code"]
        == "email_verification_required"
    )


def test_reset_revokes_all_sessions_and_token_replay(data):
    uid = data[0][0]
    a = client(uid)
    b = client(uid)
    with Session.begin() as db:
        c = issue(db, db.get(User, uid), "reset", "u0@example.test")
        payload = {
            "challenge_id": str(c.id),
            "token": challenge_token(c),
            "password": "new-password-1234",
            "password_confirm": "new-password-1234",
        }
    guest = TestClient(app)
    guest.get("/")
    guest.headers["X-CSRF-Token"] = guest.cookies["labseat_pre_csrf"]
    assert guest.post("/auth/password-reset/confirm", json=payload).status_code == 200
    assert a.get("/me").status_code == b.get("/me").status_code == 401
    assert guest.post("/auth/password-reset/confirm", json=payload).status_code == 400
    with Session() as db:
        assert hasher.verify(db.get(User, uid).password_hash, payload["password"])


def test_change_password_rotates_current_and_revokes_other(data):
    uid = data[0][0]
    with Session.begin() as db:
        db.get(User, uid).password_hash = hasher.hash("current-password")
    a = client(uid)
    b = client(uid)
    response = a.post(
        "/auth/password/change",
        json={
            "current_password": "current-password",
            "password": "new-password-1234",
            "password_confirm": "new-password-1234",
        },
    )
    assert response.status_code == 200
    assert a.get("/me").status_code == 200 and b.get("/me").status_code == 401


def test_rate_limits_survive_rejected_transaction(data):
    for _ in range(2):
        throttle("fixture", "recipient", 2, 3600)
    for _ in range(2):
        with pytest.raises(Problem) as e, Session.begin():
            throttle("fixture", "recipient", 2, 3600)
        assert e.value.status == 429


def test_last_admin_and_lock_revoke(data):
    with Session.begin() as db:
        db.get(User, data[0][1]).role = "admin"
    admin = client(data[0][1])
    student = client(data[0][0])
    response = admin.patch(
        f"/admin/users/{data[0][1]}", json={"role": "student", "reason": "fixture"}
    )
    assert response.status_code == 409 and response.json()["code"] == "last_admin"
    assert (
        admin.patch(
            f"/admin/users/{data[0][0]}", json={"status": "LOCKED", "reason": "fixture"}
        ).status_code
        == 200
    )
    assert student.get("/me").status_code == 401
    assert admin.get("/admin/users?q=u0").json()["total"] > 0


def test_staff_assignment_lookup_mask_reveal_and_revocation(data):
    uid = data[0][1]
    rid, code = confirmed(data)
    with Session.begin() as db:
        db.get(User, uid).role = "staff"
        db.get(User, data[0][0]).cccd = "012345678901"
    c = client(uid)
    assert (
        c.post("/staff/check-ins/lookup", json={"ticket_code": code}).status_code == 404
    )
    with Session.begin() as db:
        db.add(StaffAssignment(session_id=data[1], user_id=uid, assigned_by=data[0][2]))
    response = c.post("/staff/check-ins/lookup", json={"ticket_code": code})
    assert response.status_code == 200, response.text
    assert (
        response.json()["profile"]["cccd"].endswith("8901")
        and "01234567" not in response.text
    )
    assert c.post(f"/staff/check-ins/{rid}/identity").json()["cccd"] == "012345678901"
    assert c.get("/admin/users").status_code == 403
    with Session.begin() as db:
        db.delete(db.get(StaffAssignment, (data[1], uid)))
    assert c.post("/staff/check-ins", json={"ticket_code": code}).status_code == 404
    with Session() as db:
        assert db.get(Reservation, rid).status == "CONFIRMED"
        assert db.scalar(
            select(AdminAudit).where(AdminAudit.action == "checkin_identity_view")
        )


def test_deadline_enforced_without_scheduler_and_manual_reopen(data):
    rid, code = confirmed(data)
    with Session.begin() as db:
        db.get(User, data[0][1]).role = "admin"
        lab = db.get(LabSession, data[1])
        lab.checkin_close_mode = "custom"
        lab.checkin_closes_at = booking.now(db) - timedelta(seconds=1)
    c = client(data[0][1])
    assert c.post("/admin/check-ins", json={"ticket_code": code}).status_code == 409
    with Session.begin() as db:
        db.get(LabSession, data[1]).checkin_close_mode = "manual"
    assert c.post("/admin/check-ins", json={"ticket_code": code}).status_code == 200


class Email:
    def __init__(self):
        self.calls = []

    def send_message(self, to, message, key):
        self.calls.append((to, message, key))
        return "fixture-provider-id"


def test_jobs_delivery_dedup_out_of_order_suppression_and_retry_window(data):
    rid, _ = confirmed(data)
    email = Email()
    with Session.begin() as db:
        job = enqueue(db, data[0][0], "ticket", "u0@example.test", rid)
        jid = job.id
    dispatch(jid, email)
    dispatch(jid, email)
    assert len(email.calls) == 1 and email.calls[0][2] == jid
    with Session.begin() as db:
        stamp = booking.now(db).timestamp()
        event = {
            "message-id": "fixture-provider-id",
            "event": "delivered",
            "ts_event": stamp,
        }
        receive_webhook(db, [event, event])
        process_webhooks(db)
    with Session.begin() as db:
        assert db.get(EmailJob, jid).status == "DELIVERED"
        receive_webhook(
            db,
            {
                "message-id": "fixture-provider-id",
                "event": "request",
                "ts_event": stamp + 1,
            },
        )
        process_webhooks(db)
    with Session.begin() as db:
        assert db.get(EmailJob, jid).status == "DELIVERED"
        receive_webhook(
            db,
            {
                "message-id": "fixture-provider-id",
                "event": "hard_bounce",
                "ts_event": stamp + 2,
            },
        )
        process_webhooks(db)
    with Session() as db:
        assert db.get(EmailSuppression, "u0@example.test")
    with Session.begin() as db:
        j = enqueue(db, data[0][0], "ticket", "other@example.test", rid)
        j.status = "SENDING"
        j.send_started_at = j.last_attempt_at = booking.now(db) - timedelta(minutes=30)
        unknown = j.id
    dispatch(unknown, email)
    with Session() as db:
        assert db.get(EmailJob, unknown).status == "UNKNOWN"
    assert len(email.calls) == 1


def test_webhook_auth_and_forgot_generic(data, monkeypatch):
    monkeypatch.setenv("BREVO_WEBHOOK_TOKEN", "fixture-secret-" + "x" * 32)
    c = TestClient(app)
    c.get("/")
    c.headers["X-CSRF-Token"] = c.cookies["labseat_pre_csrf"]
    assert c.post("/webhooks/brevo", json={}).status_code == 403
    one = c.post("/auth/password-reset/request", json={"email": "u0@example.test"})
    two = c.post("/auth/password-reset/request", json={"email": "absent@example.test"})
    assert one.status_code == two.status_code == 202 and one.json() == two.json()


def test_cancel_batch_and_history_delete_guard(data):
    rid, code = confirmed(data)
    with Session.begin() as db:
        db.get(User, data[0][1]).role = "admin"
        event = Event(name="fixture-cancel", session_type="practice")
        db.add(event)
        db.flush()
        eid = event.id
        db.get(LabSession, data[1]).event_id = eid
    c = client(data[0][1])
    assert c.delete(f"/admin/events/{eid}").status_code == 409
    assert (
        c.post(
            f"/admin/events/{eid}/cancel", json={"reason": "fixture cancellation"}
        ).status_code
        == 202
    )
    assert c.post("/admin/check-ins", json={"ticket_code": code}).status_code == 409
    from app.modules.admin.lifecycle import cancel_batch

    with Session.begin() as db:
        assert cancel_batch(db) == 1
    with Session.begin() as db:
        assert cancel_batch(db) == 0
    with Session() as db:
        assert db.get(Reservation, rid).status == "CANCELLED"


def test_gc_quarantine_and_reference_protection(data, tmp_path, monkeypatch):
    from app.maintenance import gc_objects

    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    path = tmp_path / "users" / "old.jpg"
    path.parent.mkdir()
    path.write_bytes(b"fixture")
    old = __import__("time").time() - 3 * 86400
    os.utime(path, (old, old))
    assert gc_objects(False) == 1 and path.exists()
    assert gc_objects(True) == 0 and path.exists()
    with Session.begin() as db:
        obj = db.get(StorageObject, "users/old.jpg")
        obj.quarantine_at = booking.now(db) - timedelta(hours=25)
        db.get(User, data[0][0]).avatar_key = "users/old.jpg"
    assert gc_objects(True) == 0 and path.exists()
    with Session.begin() as db:
        db.get(User, data[0][0]).avatar_key = None
    gc_objects(True)
    with Session.begin() as db:
        db.get(StorageObject, "users/old.jpg").quarantine_at = booking.now(
            db
        ) - timedelta(hours=25)
    assert gc_objects(True) == 1 and not path.exists()


def test_maintenance_dry_run_does_not_revoke_or_anonymize(data, tmp_path, monkeypatch):
    from app.maintenance import run

    monkeypatch.setenv("LOCAL_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    with Session.begin() as db:
        u = db.get(User, data[0][0])
        u.last_activity_at = booking.now(db) - timedelta(days=400)
        u.anonymization_notice_at = booking.now(db) - timedelta(days=40)
        u.anonymization_notice_delivered_at = booking.now(db) - timedelta(days=35)
    result = run(False)
    assert result["anonymizations"] == 1
    with Session() as db:
        assert db.get(User, data[0][0]).status == "ACTIVE"
    assert run(True)["anonymizations"] == 1
    with Session() as db:
        assert db.get(User, data[0][0]).status == "ANONYMIZED"


def test_auth_email_payload_has_no_persisted_bearer_token(data):
    uid = data[0][0]
    with Session.begin() as db:
        challenge = issue(db, db.get(User, uid), "verify", "u0@example.test")
        token = challenge_token(challenge)
        jid = db.scalar(select(EmailJob.id).where(EmailJob.kind == "verify"))
    email = Email()
    dispatch(jid, email)
    assert token in email.calls[0][1]["html"]
    with Session() as db:
        assert token not in str(db.get(EmailJob, jid).context)
        assert "__LABSEAT_AUTH_TOKEN__" in str(db.get(EmailJob, jid).context)


def test_parallel_authenticated_rate_limits_keep_pool_progress(data):
    from concurrent.futures import ThreadPoolExecutor

    clients = [client(uid) for uid in data[0][:8]]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda c: c.post("/auth/email-verification/request").status_code,
                clients,
            )
        )
    assert results == [202] * 8
    from app.infrastructure.database.session import engine, counter_sessions
    from app.config import database_pool

    assert (
        engine.pool.size() + counter_sessions().kw["bind"].pool.size()
        <= database_pool()
    )


def test_resend_limits_use_full_sixty_second_cooldown(data):
    rid, _ = confirmed(data)
    c = client(data[0][0])
    assert c.post(f"/me/tickets/{rid}/email-resends").status_code == 202
    assert c.post(f"/me/tickets/{rid}/email-resends").status_code == 429


def test_privacy_review_requires_admin_reason_and_protects_future_booking(data):
    rid, _ = confirmed(data)
    with Session.begin() as db:
        db.get(User, data[0][1]).role = "admin"
        u = db.get(User, data[0][0])
        u.last_activity_at = booking.now(db) - timedelta(days=400)
        u.email_verified_at = None
    c = client(data[0][1])
    assert any(
        u["id"] == str(data[0][0]) for u in c.get("/admin/privacy-review").json()
    )
    path = f"/admin/users/{data[0][0]}/anonymize"
    assert (
        c.post(path, json={"reason": "Reviewed fixture"}).json()["code"]
        == "privacy_future_booking"
    )
    with Session.begin() as db:
        db.get(Reservation, rid).status = "CANCELLED"
    assert c.post(path, json={"reason": "Reviewed fixture"}).status_code == 200


def test_soft_bounce_is_provider_retry_not_a_new_send(data):
    rid, _ = confirmed(data)
    with Session.begin() as db:
        jid = enqueue(db, data[0][0], "ticket", "u0@example.test", rid).id
    from app.modules.notifications.brevo import EmailProviderError

    class DeferredEmail(Email):
        def send_message(self, to, message, key):
            self.calls.append(key)
            with Session.begin() as db:
                receive_webhook(
                    db,
                    {
                        "message-id": "deferred-provider-id",
                        "event": "soft_bounce",
                        "X-Mailin-custom": str(key),
                        "ts_event": booking.now(db).timestamp(),
                    },
                )
                process_webhooks(db)
            raise EmailProviderError("Ambiguous network outcome")

    email = DeferredEmail()
    with pytest.raises(EmailProviderError):
        dispatch(jid, email)
    dispatch(jid, email)
    assert len(email.calls) == 1
    with Session() as db:
        assert db.get(EmailJob, jid).status == "SOFT_BOUNCE"
