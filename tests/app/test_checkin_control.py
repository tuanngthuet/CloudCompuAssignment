"""Manual check-in policy, admin-only inspection, PII boundaries and locked transitions."""
import os
import pytest
if not os.getenv('TEST_DATABASE_URL'):
    pytest.skip('Disposable PostgreSQL required',allow_module_level=True)
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from test_db import clean_db, data, authenticated_client
from app.main import app
from app.infrastructure.database.session import Session
from app.models import User, Reservation, LabSession, AuditEvent, CheckinPolicyEvent
import app.modules.booking.service as svc


@pytest.fixture
def setup(data):
    users, lab, seats, _ = data
    with Session.begin() as db:
        db.get(User, users[1]).role = 'admin'
        owner = db.get(User, users[0])
        owner.full_name = 'Nguyễn Văn An'; owner.cccd = '012345678901'; owner.email = 'an@example.test'; owner.phone = ''
        db.get(LabSession, lab).checkin_enabled = False
        reservation, _ = svc.hold(db, users[0], lab, seats[0])
        code = svc.transition(db, users[0], reservation.id).ticket_code
        rid = reservation.id
    with authenticated_client(users[1]) as admin, authenticated_client(users[0]) as student:
        yield admin, student, rid, code, lab, users


def lookup(client, code):
    return client.post('/admin/check-ins/lookup',json={'ticket_code':str(code)})


def toggle(client, lab, enabled):
    return client.patch(f'/admin/lab-sessions/{lab}/check-in',json={'enabled':enabled})


def test_inspection_needs_admin_and_csrf_and_exposes_only_profile_fields(setup):
    admin, student, rid, code, lab, _ = setup
    assert lookup(TestClient(app),code).status_code == 401
    assert lookup(student,code).status_code == 403
    assert admin.post('/admin/check-ins/lookup',json={'ticket_code':code},headers={'X-CSRF-Token':'bad'}).status_code == 403
    result = lookup(admin,code); assert result.status_code == 200
    result = result.json()
    assert result['profile'] == dict(username='u0',full_name='Nguyễn Văn An',cccd='012345678901',email='an@example.test',phone='',avatar_url=None)
    assert result['ticket']['reservation_id'] == str(rid) and not result['can_check_in']
    assert result['session']['checkin_enabled'] is False
    assert set(result['profile']) == {'username','full_name','cccd','email','phone','avatar_url'}
    assert student.get(f'/admin/check-ins/{rid}/avatar').status_code == 403
    assert TestClient(app).get(f'/admin/check-ins/{rid}/avatar').status_code == 401
    with Session() as db:
        assert db.get(Reservation,rid).status == 'CONFIRMED'
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action=='CHECKED_IN')) == 0
    assert '012345678901' not in TestClient(app).get('/lab-sessions').text


def test_lookup_accepts_registration_id_and_unknown_ticket_is_safe(setup):
    admin, _, rid, code, _, _ = setup
    assert lookup(admin,rid).json()['ticket']['ticket_code'] == code
    assert lookup(admin,'unknown-valid-length-token').status_code == 404


def test_manual_open_allows_early_checkin_and_repeated_confirmation_is_idempotent(setup):
    admin, _, rid, code, lab, _ = setup
    with Session.begin() as db:
        row = db.get(LabSession,lab); now = svc.now(db)
        row.open_at=now-timedelta(hours=1);row.close_at=now+timedelta(hours=1)
        row.start_at=now+timedelta(days=1);row.end_at=now+timedelta(days=1,hours=1)
    assert admin.post('/admin/check-ins',json={'ticket_code':code}).status_code == 409
    assert toggle(admin,lab,True).status_code == 200
    assert lookup(admin,code).json()['can_check_in'] is True
    first = admin.post('/admin/check-ins',json={'ticket_code':code}); assert first.status_code == 200
    second = admin.post('/admin/check-ins',json={'ticket_code':str(rid)})
    assert second.json()['checked_in_at'] == first.json()['checked_in_at']
    info = lookup(admin,code).json(); assert not info['can_check_in'] and info['ticket']['status'] == 'CHECKED_IN'
    assert toggle(admin,lab,False).status_code == 200
    assert admin.post('/admin/check-ins',json={'ticket_code':code}).json()['checked_in_at'] == first.json()['checked_in_at']
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.reservation_id==rid,AuditEvent.action=='CHECKED_IN')) == 1


def test_manual_open_controls_checkin_even_after_end_time(setup):
    admin, _, _, code, lab, _ = setup
    with Session.begin() as db:
        row=db.get(LabSession,lab);now=svc.now(db)
        row.open_at=now-timedelta(hours=4);row.close_at=now-timedelta(hours=3)
        row.start_at=now-timedelta(hours=2);row.end_at=now-timedelta(hours=1)
    toggle(admin,lab,True)
    assert admin.post('/admin/check-ins',json={'ticket_code':code}).status_code == 200


def test_closing_after_lookup_is_rechecked_and_policy_is_audited(setup):
    admin, student, rid, code, lab, _ = setup
    assert toggle(student,lab,True).status_code == 403
    assert admin.patch(f'/admin/lab-sessions/{lab}/check-in',json={'enabled':True},headers={'X-CSRF-Token':'bad'}).status_code == 403
    assert admin.patch(f'/admin/lab-sessions/{lab}/check-in',json={'enabled':'false'}).status_code == 422
    toggle(admin,lab,True); assert lookup(admin,code).json()['can_check_in']
    toggle(admin,lab,False)
    response=admin.post('/admin/check-ins',json={'ticket_code':code})
    assert response.status_code == 409 and response.json()['code'] == 'checkin_closed'
    toggle(admin,lab,False)  # same desired state: no duplicate policy event
    with Session() as db:
        assert db.get(Reservation,rid).status == 'CONFIRMED'
        assert list(db.scalars(select(CheckinPolicyEvent.enabled).where(CheckinPolicyEvent.session_id==lab).order_by(CheckinPolicyEvent.created_at))) == [True,False]


def test_cancelled_ticket_never_has_checkin_permission(setup):
    admin, _, rid, code, lab, users=setup
    with Session.begin() as db: svc.transition(db,users[0],rid,action='cancel')
    toggle(admin,lab,True)
    assert lookup(admin,code).json()['can_check_in'] is False
    assert admin.post('/admin/check-ins',json={'ticket_code':code}).status_code == 409


def test_concurrent_checkins_create_one_audit_record(setup):
    admin, _, rid, code, lab, users=setup
    toggle(admin,lab,True)
    def check():
        with Session.begin() as db:
            return svc.transition(db,users[1],action='check-in',ticket_code=code).checked_in_at
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:check(),range(2)))
    assert results[0] == results[1]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.reservation_id==rid,AuditEvent.action=='CHECKED_IN')) == 1


def test_exclusive_policy_lock_prevents_checkin_using_stale_open_state(setup):
    admin, _, rid, code, lab, users=setup
    toggle(admin,lab,True)
    def check():
        with Session.begin() as db:
            try: return svc.transition(db,users[1],action='check-in',ticket_code=code).status
            except svc.Problem as exc: return exc.code
    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session.begin() as db:
            row=db.scalar(select(LabSession).where(LabSession.id==lab).with_for_update())
            row.checkin_enabled=False;db.flush()
            pending=pool.submit(check)
        assert pending.result(timeout=5) == 'checkin_closed'
    with Session() as db: assert db.get(Reservation,rid).status == 'CONFIRMED'


@pytest.mark.parametrize('expired', [False,True])
def test_unconfirmed_or_expired_hold_is_visible_but_cannot_check_in(setup, expired):
    from app.models import SessionSeat
    admin, _, confirmed_id, _, lab, users=setup
    toggle(admin,lab,True)
    with Session.begin() as db:
        occupied=db.get(Reservation,confirmed_id).seat_id
        other=db.scalar(select(SessionSeat.seat_id).where(SessionSeat.session_id==lab,SessionSeat.seat_id!=occupied).limit(1))
        held,_=svc.hold(db,users[2],lab,other);rid=held.id
        if expired: held.hold_expires_at=svc.now(db)-timedelta(seconds=1)
    info=lookup(admin,rid).json()
    assert info['ticket']['status'] == ('EXPIRED' if expired else 'HELD')
    assert info['can_check_in'] is False
    assert admin.post('/admin/check-ins',json={'ticket_code':str(rid)}).status_code == 409
