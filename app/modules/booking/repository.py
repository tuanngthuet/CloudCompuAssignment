"""Booking synchronization. Callers own the transaction; no commits here."""
import logging
import time
from sqlalchemy import select
from app.models import User, LabSession, SessionSeat, Reservation
from app.errors import Problem

logger = logging.getLogger('labseat.booking')


def lock(db, owner, session, seat, actor=None):
    started = time.monotonic()
    # Audit FK can reference a different administrator. Lock both users in one
    # global order before room locks, avoiding owner/admin cross-check-in cycles.
    users = {owner, actor or owner}
    locked_users=list(db.scalars(select(User).where(User.id.in_(users)).order_by(User.id).with_for_update().execution_options(populate_existing=True)))
    from app.modules.accounts.service import active
    active(next((user for user in locked_users if user.id==(actor or owner)),None))
    # SHARE permits independent room bookings but conflicts with admin UPDATE/DELETE.
    # populate_existing is essential if auth/route code loaded this row earlier.
    lab = db.scalar(select(LabSession).where(LabSession.id == session)
                    .with_for_update(read=True).execution_options(populate_existing=True))
    if lab is None:
        raise Problem(404, 'not_found', 'Không có ca')
    # Expiry cleanup may write the actor's previous room as well as the target.
    # Lock every affected room in a stable order to avoid opposite-room deadlocks.
    affected = set(db.scalars(select(Reservation.seat_id).where(
        Reservation.user_id == owner, Reservation.session_id == session,
        Reservation.status == 'HELD')))
    affected.add(seat)
    rows = list(db.scalars(select(SessionSeat).where(SessionSeat.session_id == session,
        SessionSeat.seat_id.in_(affected)).order_by(SessionSeat.seat_id).with_for_update()))
    if not any(row.seat_id == seat for row in rows):
        raise Problem(404, 'not_found', 'Không có phòng trong ca')
    from app.infrastructure.observability.metrics import emit
    emit('BookingLockMs', (time.monotonic() - started) * 1000)
    return lab
