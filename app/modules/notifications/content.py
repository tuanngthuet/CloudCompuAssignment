"""LABSEAT ticket email. No profiles or ticket codes are placed in remote URLs."""
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
import hashlib
import hmac
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape
from app.models import LabSession, Event, Room, Seat


@dataclass(frozen=True)
class EmailTicket:
    id: UUID
    ticket_code: str = field(repr=False)
    event_name: str
    room_name: str
    seat_code: str
    start_at: datetime
    end_at: datetime
    session_kind: str = 'ca thực hành'


def ticket_details(db, reservation):
    lab = db.get(LabSession, reservation.session_id)
    event = db.get(Event, lab.event_id) if lab.event_id else None
    room = db.get(Room, lab.room_id)
    seat = db.get(Seat, reservation.seat_id)
    return EmailTicket(reservation.id, reservation.ticket_code,
        event.name if event else room.name, room.name, seat.seat_code,
        lab.start_at, lab.end_at, 'ca thi' if event and event.session_type == 'exam' else 'ca thực hành')


def qr_png(ticket_code):
    output = BytesIO()
    qrcode.make(ticket_code).save(output, format='PNG')
    return output.getvalue()


def image_signature(reservation_id, ticket_code):
    # A separate scoped capability, not the check-in code. The existing random
    # 256-bit ticket is the HMAC key; all API tasks share it through PostgreSQL.
    return hmac.new(ticket_code.encode(), f'labseat-email-qr:v1:{reservation_id}'.encode(), hashlib.sha256).hexdigest()


@lru_cache(maxsize=1)
def templates():
    return Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[2] / 'templates/emails'),
        autoescape=select_autoescape(['html', 'xml']), keep_trailing_newline=True)


def render_confirmation(ticket, base_url, support_email='', *, preview=False):
    base_url = base_url.rstrip('/')
    local_start = ticket.start_at.astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
    local_end = ticket.end_at.astimezone(ZoneInfo('Asia/Ho_Chi_Minh'))
    context = dict(ticket=ticket, website=base_url, support_email=support_email,
        date=local_start.strftime('%d/%m/%Y'),
        time=f'{local_start:%H:%M} – {local_end:%H:%M}' if local_start.date() == local_end.date() else f'{local_start:%H:%M %d/%m/%Y} – {local_end:%H:%M %d/%m/%Y}',
        logo_url='labseat-logo.png' if preview else f'{base_url}/static/labseat-email.png',
        qr_url='qr.png' if preview else f'{base_url}/email/tickets/{ticket.id}/{image_signature(ticket.id, ticket.ticket_code)}/qr.png')
    return templates().get_template('reservation-confirmed.html').render(**context)
