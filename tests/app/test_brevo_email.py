"""Brevo HTTP contract and email content without credentials or real network."""
import base64
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
from uuid import UUID
import httpx
import pytest
from PIL import Image
from app.modules.notifications.brevo import BrevoEmail, BrevoSettings, EmailProviderError
from app.modules.notifications.content import EmailTicket, render_confirmation, image_signature, qr_png


@pytest.fixture
def ticket():
    start = datetime(2026, 11, 20, 1, tzinfo=timezone.utc)
    return EmailTicket(UUID('00000000-0000-4000-8000-000000000001'), 'synthetic-ticket-secret',
        'Thực hành Python', 'Khu thực hành', 'A101', start, start + timedelta(hours=2))


@pytest.fixture
def settings():
    return BrevoSettings('fixture-api-key', 'verified@example.test', 'LABSEAT', 'https://labseat.example.test', 'support@example.test')


def test_brevo_request_contract_and_attached_qr(ticket, settings):
    captured = []
    def handler(request):
        assert str(request.url) == 'https://api.brevo.com/v3/smtp/email'
        assert request.headers['api-key'] == settings.api_key
        body = json.loads(request.content); captured.append(body)
        return httpx.Response(201, json={'messageId': '<fixture-message-id>'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert BrevoEmail(settings, client).send('recipient@example.test', ticket) == '<fixture-message-id>'
    payload = captured[0]
    assert payload['to'] == [{'email': 'recipient@example.test'}]
    assert payload['sender'] == {'email': settings.sender_email, 'name': 'LABSEAT'}
    assert 'LABSEAT' in payload['subject']
    assert payload['attachment'][0]['name'] == 'labseat-qr.png'
    content = base64.b64decode(payload['attachment'][0]['content'])
    assert content == qr_png(ticket.ticket_code)
    assert Image.open(BytesIO(content)).format == 'PNG'
    import cv2
    import numpy as np
    pixels = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert cv2.QRCodeDetector().detectAndDecode(pixels)[0] == ticket.ticket_code
    html = payload['htmlContent']
    assert '20/11/2026' in html and '08:00 – 10:00' in html
    assert 'labseat-email.png' in html and 'Thực hành Python' in html and 'A101' in html
    assert ticket.ticket_code not in html and 'data:image' not in html and 'cid:' not in html
    assert image_signature(ticket.id, ticket.ticket_code) in html
    assert 'Hệ thống đăng kí ca thi và thực hành' in html
    assert 'cccd' not in json.dumps(payload).lower()


@pytest.mark.parametrize('status', [400, 401, 403, 429, 500, 302])
def test_brevo_failure_is_sanitized_and_not_retried(ticket, settings, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'message': 'private-recipient fixture-api-key'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailProviderError) as exc:
            BrevoEmail(settings, client).send('private-recipient@example.test', ticket)
    assert len(calls) == 1
    assert str(status) in str(exc.value)
    assert settings.api_key not in str(exc.value) and 'private-recipient' not in str(exc.value)


def test_timeout_is_ambiguous_without_leaking_secret(ticket, settings):
    def handler(request):
        raise httpx.ReadTimeout('fixture-api-key private-recipient', request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailProviderError) as exc:
            BrevoEmail(settings, client).send('recipient@example.test', ticket)
    assert 'unknown' in str(exc.value) and settings.api_key not in str(exc.value)


@pytest.mark.parametrize('body', [{}, {'messageId': None}, {'messageId': ''}, {'messageId': 'x'*255}])
def test_invalid_provider_ack_is_not_success(ticket, settings, body):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(201, json=body))) as client:
        with pytest.raises(EmailProviderError): BrevoEmail(settings, client).send('recipient@example.test', ticket)


def test_html_escapes_untrusted_event_and_room(ticket):
    html = render_confirmation(replace(ticket, event_name='<script>alert(1)</script>', room_name='<img src=x onerror=alert(1)>'), 'https://labseat.example.test')
    assert '<script>' not in html and '<img src=x' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html


@pytest.mark.parametrize('url', ['http://labseat.example.test', 'javascript:alert(1)', 'https://name:secret@labseat.example.test', 'https://labseat.example.test?token=secret', 'https://labseat.example.test/#fragment'])
def test_real_email_requires_clean_https_url(settings, url):
    with pytest.raises(ValueError): replace(settings, base_url=url)


def test_secret_file_is_supported_and_key_is_not_in_repr(tmp_path, monkeypatch, settings):
    secret = tmp_path / 'key'; secret.write_text('fixture-api-key\n')
    monkeypatch.delenv('BREVO_API_KEY', raising=False)
    monkeypatch.setenv('BREVO_API_KEY_FILE', str(secret))
    monkeypatch.setenv('BREVO_FROM_EMAIL', settings.sender_email)
    monkeypatch.setenv('EMAIL_PUBLIC_BASE_URL', settings.base_url)
    value = BrevoSettings.from_environment()
    assert value.api_key == 'fixture-api-key' and value.api_key not in repr(value)
    monkeypatch.setenv('BREVO_API_KEY', 'another-fixture')
    with pytest.raises(ValueError): BrevoSettings.from_environment()
