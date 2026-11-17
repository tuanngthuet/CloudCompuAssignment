from datetime import timedelta
import secrets
from sqlalchemy import select, func, or_
from app.models import LabSession, Reservation, AuditEvent, Seat

ACTIVE = ('HELD', 'CONFIRMED', 'CHECKED_IN')

from app.errors import Problem

def require(condition, status=409, code='conflict', message='Trạng thái hoặc thời gian không hợp lệ'):
    if not condition:
        raise Problem(status, code, message)

def now(db):
    return db.scalar(select(func.clock_timestamp()))

def lock(db, owner, session, seat, actor=None):
    from .repository import lock as acquire
    lab = acquire(db, owner, session, seat, actor=actor)
    return lab, now(db)


def audit(db, actor, reservation, action):
    db.flush()
    db.add(AuditEvent(actor_id=actor, reservation_id=reservation.id, action=action))
    from app.models import PlatformEvent
    db.add(PlatformEvent(kind='availability',subject_id=reservation.session_id))

def hold(db, actor, session, seat):
    lab, clock = lock(db, actor, session, seat)
    from app.modules.profiles.service import require_for_exam
    require_for_exam(db,actor,lab)
    require(lab.open_at <= clock < lab.close_at)
    expired = list(db.scalars(select(Reservation).where(Reservation.session_id == session, Reservation.status == 'HELD', Reservation.hold_expires_at <= clock, or_(Reservation.user_id == actor, Reservation.seat_id == seat))))
    for old in expired:
        old.status = 'EXPIRED'
        audit(db, actor, old, 'EXPIRED')
    db.flush()
    current = db.scalar(select(Reservation).where(Reservation.session_id == session, Reservation.user_id == actor, Reservation.status.in_(ACTIVE)))
    if current:
        require(current.seat_id == seat and current.status == 'HELD')
        return current, clock
    if lab.event_id:
        other = db.scalar(select(Reservation.id).join(LabSession,LabSession.id==Reservation.session_id).where(
            LabSession.event_id==lab.event_id, Reservation.user_id==actor,
            or_(Reservation.status.in_(('CONFIRMED','CHECKED_IN')), (Reservation.status=='HELD') & (Reservation.hold_expires_at>clock))))
        require(other is None,409,'active_registration','Bạn đã có đăng kí hoặc đang giữ một suất trong ca này')
    target=db.get(Seat,seat)
    occupied=set(db.scalars(select(Reservation.slot).where(Reservation.session_id==session,Reservation.seat_id==seat,Reservation.status.in_(ACTIVE))))
    slot=next((i for i in range(target.capacity) if i not in occupied),None)
    require(slot is not None,409,'sold_out','Phòng đã đủ số người đăng kí')
    from app.infrastructure.redis.admission import guard
    guard(db, actor, lab)
    r = Reservation(user_id=actor, session_id=session, seat_id=seat, status='HELD', slot=slot, hold_expires_at=min(clock + timedelta(seconds=180), lab.close_at))
    db.add(r)
    audit(db, actor, r, 'HELD')
    return r, clock

def transition(db, actor, reservation_id=None, action='confirm', ticket_code=None):
    query = select(Reservation).where(Reservation.ticket_code == ticket_code) if ticket_code else select(Reservation).where(Reservation.id == reservation_id)
    r = db.scalar(query)
    require(r is not None and (action == 'check-in' or r.user_id == actor), 404, 'not_found', 'Không có đăng kí')
    lab, clock = lock(db, r.user_id, r.session_id, r.seat_id, actor=actor)
    db.refresh(r)
    if action == 'confirm':
        if r.status in ('CONFIRMED','CHECKED_IN'):
            return r
        from app.modules.profiles.service import require_for_exam
        require_for_exam(db,r.user_id,lab)
        require(r.status == 'HELD' and clock < r.hold_expires_at and clock < lab.close_at)
        r.status, r.ticket_code = 'CONFIRMED', r.ticket_code or secrets.token_urlsafe(32)
        from app.models import OutboxEvent
        db.add(OutboxEvent(reservation_id=r.id, event_type='ReservationConfirmed'))
    elif action == 'cancel':
        if r.status == 'CANCELLED':
            return r
        require((r.status == 'HELD' and clock < r.hold_expires_at) or (r.status == 'CONFIRMED' and clock < lab.start_at))
        r.status = 'CANCELLED'
    else:
        from app.models import User
        from app.modules.checkin.policy import effective,scope
        scope(db,db.get(User,actor),lab,lock=True)
        if r.status == 'CHECKED_IN':
            return r
        require(r.status == 'CONFIRMED',409,'ticket_not_eligible','Vé không đủ điều kiện check-in')
        require(effective(db,lab),409,'checkin_closed','Ca chưa mở check-in')
        r.status, r.checked_in_at = 'CHECKED_IN', clock
    audit(db, actor, r, r.status)
    return r
