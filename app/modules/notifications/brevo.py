"""Brevo transactional HTTP API, bounded I/O and no automatic send retries."""

import base64
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import httpx
from .content import qr_png, render_confirmation


class EmailProviderError(RuntimeError):
    """Safe to report without provider response bodies, recipients or credentials."""


def email_address(value, name):
    if not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", value):
        raise ValueError(f"{name} must be an email address")
    return value


@dataclass(frozen=True)
class BrevoSettings:
    api_key: str = field(repr=False)
    sender_email: str
    sender_name: str
    base_url: str
    support_email: str = ""

    def __post_init__(self):
        if not self.api_key or any(c.isspace() for c in self.api_key):
            raise ValueError("BREVO_API_KEY must be configured")
        email_address(self.sender_email, "BREVO_FROM_EMAIL")
        if (
            not self.sender_name
            or len(self.sender_name) > 100
            or any(ord(c) < 32 for c in self.sender_name)
        ):
            raise ValueError("BREVO_FROM_NAME is invalid")
        url = urlsplit(self.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or any(c.isspace() or ord(c) < 32 for c in self.base_url)
        ):
            raise ValueError(
                "EMAIL_PUBLIC_BASE_URL must be a public HTTPS website URL without credentials/query/fragment"
            )
        if self.support_email:
            email_address(self.support_email, "EMAIL_SUPPORT_EMAIL")

    @classmethod
    def from_environment(cls):
        key = os.getenv("BREVO_API_KEY", "")
        key_file = os.getenv("BREVO_API_KEY_FILE", "")
        if key and key_file:
            raise ValueError("Use either BREVO_API_KEY or BREVO_API_KEY_FILE")
        if key_file:
            key = Path(key_file).read_text().strip()
        return cls(
            key,
            os.getenv("BREVO_FROM_EMAIL", ""),
            os.getenv("BREVO_FROM_NAME", "LABSEAT"),
            os.getenv("EMAIL_PUBLIC_BASE_URL", "").rstrip("/"),
            os.getenv("EMAIL_SUPPORT_EMAIL", ""),
        )


class BrevoEmail:
    URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self, settings=None, client=None):
        self.settings = (
            settings if settings is not None else BrevoSettings.from_environment()
        )
        self.client = client  # HTTPX MockTransport is injected by tests; no real mail.

    def send(self, recipient, ticket):
        settings = self.settings
        payload = {
            "sender": {"name": settings.sender_name, "email": settings.sender_email},
            "to": [{"email": recipient}],
            "subject": "LABSEAT — Xác nhận đăng kí thành công",
            "htmlContent": render_confirmation(
                ticket, settings.base_url, settings.support_email
            ),
            "attachment": [
                {
                    "name": "labseat-qr.png",
                    "content": base64.b64encode(qr_png(ticket.ticket_code)).decode(
                        "ascii"
                    ),
                }
            ],
            "tags": ["labseat-reservation-confirmed"],
        }
        return self._post(payload)

    def send_message(self, recipient, message, job_id):
        payload = {
            "sender": message.get("sender")
            or {"name": self.settings.sender_name, "email": self.settings.sender_email},
            "to": [{"email": recipient}],
            "subject": message["subject"],
            "htmlContent": message["html"],
            "headers": {"idempotencyKey": str(job_id), "X-Mailin-custom": str(job_id)},
            "tags": ["labseat", str(job_id)],
        }
        if message.get("qr"):
            payload["attachment"] = [
                {
                    "name": "labseat-qr.png",
                    "content": base64.b64encode(message["qr"]).decode("ascii"),
                }
            ]
        return self._post(payload)

    def _post(self, payload):
        settings = self.settings
        headers = {
            "api-key": settings.api_key,
            "accept": "application/json",
            "content-type": "application/json",
        }
        try:
            if self.client is not None:
                response = self.client.post(self.URL, json=payload, headers=headers)
            else:
                with httpx.Client(
                    timeout=httpx.Timeout(8, connect=3, pool=3),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    response = client.post(self.URL, json=payload, headers=headers)
        except httpx.HTTPError:
            raise EmailProviderError(
                "Brevo connection failed; message outcome may be unknown"
            ) from None
        if response.status_code != 201:
            try:
                duplicate = response.json().get("code") == "duplicate_parameter"
            except (ValueError, AttributeError):
                duplicate = False
            if duplicate:
                raise EmailProviderError("Brevo duplicate request; acceptance unknown")
            raise EmailProviderError(f"Brevo send failed (HTTP {response.status_code})")
        try:
            message_id = response.json()["messageId"]
            if not isinstance(message_id, str) or not 1 <= len(message_id) <= 254:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise EmailProviderError(
                "Brevo returned an invalid send acknowledgement"
            ) from None
        return message_id
