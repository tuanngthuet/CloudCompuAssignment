"""Controlled multi-connection tests on disposable PostgreSQL, never production."""
import os
import pytest
if not os.getenv('TEST_DATABASE_URL'):
    pytest.skip('Disposable DB required', allow_module_level=True)
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select, text, func
from sqlalchemy.exc import DBAPIError
from test_db import clean_db, data, authenticated_client
from app.infrastructure.database.session import Session
from app.models import LabSession, Reservation, Seat, User, IdempotencyRecord
import app.modules.booking.service as svc


def attempt(user, lab, seat):
    with Session.begin() as db:
        return svc.hold(db, user, lab, seat)[0].id


def test_unrelated_rooms_progress_while_first_transaction_open(data):
    users, lab, seats, _ = data
    with Session.begin() as first, ThreadPoolExecutor(max_workers=1) as pool:
        svc.hold(first, users[0], lab, seats[0])
        # Must commit in room2 while the room1 transaction is still holding locks.
        second = pool.submit(attempt, users[1], lab, seats[1]).result(timeout=4)
        assert second



def test_admin_exclusive_edit_waits_for_active_booking(data):
    users, lab, seats, _ = data
    def edit():
        with Session.begin() as db:
            db.execute(text("SET LOCAL lock_timeout='200ms'"))
            row=db.scalar(select(LabSession).where(LabSession.id==lab).with_for_update())
            row.close_at=svc.now(db)
    with Session.begin() as first, ThreadPoolExecutor(max_workers=1) as pool:
        svc.hold(first,users[0],lab,seats[0])
        with pytest.raises(DBAPIError) as exc:pool.submit(edit).result(timeout=4)
        assert exc.value.orig.sqlstate=='55P03'
    # The real admin route sees the committed reservation and rejects changing its schedule.
    with Session.begin() as db:db.get(User,users[2]).role='admin'
    with Session() as db:
        row=db.get(LabSession,lab)
        payload={k:getattr(row,k).isoformat() for k in ('open_at','close_at','start_at','end_at')}
        payload['room_id']=str(row.room_id)
        payload['close_at']=(row.close_at-timedelta(seconds=1)).isoformat()
    with authenticated_client(users[2]) as client:
        assert client.patch(f'/admin/lab-sessions/{lab}',json=payload).status_code==409


def test_thousand_attempts_across_five_rooms(data):
    users, lab, seats, _=data
    with Session.begin() as db:
        for seat in seats:db.get(Seat,seat).capacity=20
    with ThreadPoolExecutor(max_workers=20) as pool:
        results=list(pool.map(lambda i:attempt(users[i%100],lab,seats[i%5]), range(1000)))
    assert len(set(results))==100
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Reservation))==100
        assert not db.execute(select(Reservation.seat_id,Reservation.slot).group_by(
            Reservation.seat_id,Reservation.slot).having(func.count()>1)).all()


def test_opposite_room_expired_holds_do_not_deadlock(data):
    users,lab,seats,_=data
    first=attempt(users[0],lab,seats[0]);second=attempt(users[1],lab,seats[1])
    with Session.begin() as db:
        for rid in (first,second):db.get(Reservation,rid).hold_expires_at=svc.now(db)-timedelta(seconds=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(attempt,users[0],lab,seats[1]),pool.submit(attempt,users[1],lab,seats[0])]
        assert all(f.result(timeout=5) for f in results)


def test_idempotency_replays_exact_response_without_extending_hold(data):
    users,lab,seats,_=data
    with authenticated_client(users[0]) as client:
        body={'session_id':str(lab),'seat_id':str(seats[0])};headers={'Idempotency-Key':'test-stable-hold-key'}
        first=client.post('/holds',json=body,headers=headers)
        assert first.status_code==200
        replay=client.post('/holds',json=body,headers=headers)
        assert replay.json()==first.json()
        other=client.post('/holds',json=body|{'seat_id':str(seats[1])},headers=headers)
        assert other.status_code==409 and other.json()['code']=='idempotency_key_reused'
        with Session.begin() as db:
            import uuid
            db.get(Reservation,uuid.UUID(first.json()['hold_id'])).hold_expires_at=svc.now(db)-timedelta(seconds=1)
        assert client.post('/holds',json=body,headers=headers).json()==first.json()
        assert client.post(f'/holds/{first.json()["hold_id"]}/confirm').status_code==409
    with Session() as db:assert db.scalar(select(func.count()).select_from(IdempotencyRecord))==1


def test_concurrent_same_idempotency_key_one_mutation(data):
    users,lab,seats,_=data
    from app.modules.booking.idempotency import execute
    body={'session_id':str(lab),'seat_id':str(seats[0])}
    def request():
        with Session.begin() as db:
            def mutation():
                r,t=svc.hold(db,users[0],lab,seats[0])
                return {'hold_id':str(r.id),'expires_at':r.hold_expires_at.isoformat()}
            return execute(db,users[0],'concurrent-stable-key','hold',body,mutation)
    with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(lambda _:request(),range(20)))
    assert all(r==results[0] for r in results)
    with Session() as db:assert db.scalar(select(func.count()).select_from(Reservation))==1


def test_idempotency_rollback_does_not_persist_response(data):
    users,lab,seats,_=data
    from app.modules.booking.idempotency import execute
    with pytest.raises(RuntimeError),Session.begin() as db:
        execute(db,users[0],'rollback-stable-key','hold',{},lambda:{'hold':str(svc.hold(db,users[0],lab,seats[0])[0].id)})
        raise RuntimeError('rollback')
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord))==0
        assert db.scalar(select(func.count()).select_from(Reservation))==0


def test_invalid_and_user_scoped_idempotency_keys(data):
    users,lab,seats,_=data
    body={'session_id':str(lab),'seat_id':str(seats[0])}
    with authenticated_client(users[0]) as first,authenticated_client(users[1]) as second:
        assert first.post('/holds',json=body,headers={'Idempotency-Key':'bad key'}).status_code==422
        key={'Idempotency-Key':'same-key-different-users'}
        assert first.post('/holds',json=body,headers=key).status_code==200
        assert second.post('/holds',json=body|{'seat_id':str(seats[1])},headers=key).status_code==200


def test_confirm_and_cancel_keys_replay_authoritative_results(data):
    users,lab,seats,_=data
    with authenticated_client(users[0]) as client:
        held=client.post('/holds',json={'session_id':str(lab),'seat_id':str(seats[0])}).json()['hold_id']
        confirm={'Idempotency-Key':'stable-confirm-key'}
        first=client.post(f'/holds/{held}/confirm',headers=confirm)
        assert first.status_code==200
        assert client.post(f'/holds/{held}/confirm',headers=confirm).json()==first.json()
        cancel={'Idempotency-Key':'stable-cancel-key'}
        cancelled=client.post(f'/reservations/{held}/cancel',headers=cancel)
        assert cancelled.status_code==200 and cancelled.json()['status']=='CANCELLED'
        assert client.post(f'/reservations/{held}/cancel',headers=cancel).json()==cancelled.json()
        # Stored response is the committed successful receipt, not a fresh state transition.
        assert client.post(f'/holds/{held}/confirm',headers=confirm).json()==first.json()
        assert client.get('/me/tickets').json()[0]['status']=='CANCELLED'


def test_opposite_checkin_actors_use_consistent_user_lock_order(data):
    users,lab,seats,_=data
    with Session.begin() as db:
        for uid in users[:2]: db.get(User,uid).role='admin'
    codes=[]
    for i in (0,1):
        rid=attempt(users[i],lab,seats[i])
        with Session.begin() as db:codes.append(svc.transition(db,users[i],rid,'confirm').ticket_code)
    def check(i):
        with Session.begin() as db:
            return svc.transition(db,users[i],action='check-in',ticket_code=codes[1-i]).status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(check,(0,1)))
    assert results==['CHECKED_IN','CHECKED_IN']
