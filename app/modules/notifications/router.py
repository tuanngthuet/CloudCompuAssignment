"""Read-only, scoped email QR image. No login/session or check-in mutations."""
import hmac
from uuid import UUID
from fastapi import APIRouter, Response, Path
from app.shared.http import DB
from app.models import Reservation, LabSession
import app.modules.booking.service as svc
from .content import image_signature, qr_png

router = APIRouter()


@router.get('/email/tickets/{reservation_id}/{signature}/qr.png', include_in_schema=False)
def email_qr(reservation_id: UUID, signature: str = Path(pattern=r'^[a-f0-9]{64}$'), db=DB):
    reservation = db.get(Reservation, reservation_id)
    svc.require(reservation is not None and reservation.ticket_code is not None, 404, 'not_found', 'Không có vé')
    svc.require(hmac.compare_digest(signature, image_signature(reservation.id, reservation.ticket_code)),
                404, 'not_found', 'Không có vé')
    lab = db.get(LabSession, reservation.session_id)
    svc.require(reservation.status in ('CONFIRMED', 'CHECKED_IN') and svc.now(db) < lab.end_at,
                404, 'not_found', 'Không có vé')
    return Response(qr_png(reservation.ticket_code), media_type='image/png',
        headers={'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer', 'X-Robots-Tag': 'noindex, nofollow'})
