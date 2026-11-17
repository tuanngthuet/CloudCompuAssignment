"""Brevo confirmation and scoped QR images use disposable PostgreSQL only."""
import os
import pytest
if not os.getenv('TEST_DATABASE_URL'):
    pytest.skip('Disposable PostgreSQL required', allow_module_level=True)
from datetime import timedelta
from uuid import uuid4
import httpx
from sqlalchemy import select, func
from fastapi.testclient import TestClient
from test_db import clean_db, data
from test_notifications import confirmed, message
from app.infrastructure.database.session import Session
from app.main import app
from app.models import Reservation, NotificationDelivery, LabSession, AuditEvent
from app.modules.notifications.content import image_signature, qr_png
from app.modules.notifications.service import consume
from app.modules.notifications.brevo import BrevoEmail, BrevoSettings, EmailProviderError
import app.modules.booking.service as svc


def url(rid):
    with Session() as db:
        code = db.get(Reservation, rid).ticket_code
    return f'/email/tickets/{rid}/{image_signature(rid, code)}/qr.png', code


def test_email_qr_capability_is_read_only_scoped_and_same_as_ticket(data):
    rid = confirmed(data); path, code = url(rid)
    client = TestClient(app)
    with Session() as db: before = db.scalar(select(func.count()).select_from(AuditEvent))
    response = client.get(path)
    assert response.status_code == 200 and response.content == qr_png(code)
    assert response.headers['content-type'] == 'image/png' and 'no-store' in response.headers['cache-control']
    assert response.headers['referrer-policy'] == 'no-referrer'
    signature = path.split('/')[-2]
    invalid = ('a' if signature[0] != 'a' else 'b') + signature[1:]
    assert client.get(path.replace(signature, invalid)).status_code == 404
    assert client.get(path.replace(str(rid), str(uuid4()))).status_code == 404
    assert client.post('/admin/check-ins', json={'ticket_code': code}).status_code == 401
    with Session() as db:
        assert db.get(Reservation, rid).status == 'CONFIRMED'
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_cancelled_ticket_email_qr_is_revoked(data):
    rid = confirmed(data); path, _ = url(rid)
    with Session.begin() as db: svc.transition(db, data[0][0], rid, action='cancel')
    assert TestClient(app).get(path).status_code == 404


def test_email_image_expires_at_session_end(data):
    rid = confirmed(data); path, _ = url(rid)
    with Session.begin() as db:
        lab = db.get(LabSession, data[1]); now = svc.now(db)
        lab.open_at = now - timedelta(hours=4); lab.close_at = now - timedelta(hours=3)
        lab.start_at = now - timedelta(hours=2); lab.end_at = now - timedelta(hours=1)
    assert TestClient(app).get(path).status_code == 404


def test_brevo_failures_preserve_booking_and_retry_deduplicates(data):
    rid = confirmed(data); body = message(rid); calls = []
    settings = BrevoSettings('fixture', 'sender@example.test', 'LABSEAT', 'https://labseat.example.test')
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(429))) as client:
        with pytest.raises(EmailProviderError): consume(body, BrevoEmail(settings, client))
    with Session() as db:
        assert db.get(Reservation, rid).status == 'CONFIRMED'
        assert db.get(NotificationDelivery, (rid, 'ReservationConfirmed')).status == 'PENDING'
    def accepted(request):
        calls.append(request)
        return httpx.Response(201, json={'messageId': 'brevo-fixture-id'})
    with httpx.Client(transport=httpx.MockTransport(accepted)) as client:
        consume(body, BrevoEmail(settings, client)); consume(body, BrevoEmail(settings, client))
    assert len(calls) == 1
    with Session() as db:
        delivery = db.get(NotificationDelivery, (rid, 'ReservationConfirmed'))
        assert delivery.status == 'SENT' and delivery.provider_message_id == 'brevo-fixture-id'
