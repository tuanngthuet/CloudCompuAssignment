"""Transactions, competing consumers, provider failures and ambiguous publication."""
import json
import os
import pytest
if not os.getenv('TEST_DATABASE_URL'):
    pytest.skip('Disposable PostgreSQL required', allow_module_level=True)
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, func
from test_db import clean_db, data
from app.infrastructure.database.session import Session
from app.models import Reservation, User, OutboxEvent, NotificationDelivery
import app.modules.booking.service as svc
from app.modules.notifications.service import publish_batch, consume


class Queue:
    def __init__(self):
        self.messages = []
        self.fail = False
    def publish(self, body):
        self.messages.append(body)
        if self.fail:
            raise RuntimeError('ambiguous send')


class Email:
    def __init__(self):
        self.calls = 0
        self.fail = False
    def send(self, recipient, reservation):
        self.calls += 1
        if self.fail:
            raise RuntimeError('mock email failure')
        return 'mock-id'


def confirmed(data, email='student@example.test'):
    users, lab, seats, _ = data
    with Session.begin() as db:
        db.get(User, users[0]).email = email
        r, _ = svc.hold(db, users[0], lab, seats[0])
        rid = r.id
        svc.transition(db, users[0], rid)
    return rid


def message(rid):
    with Session() as db:
        event = db.scalar(select(OutboxEvent).where(OutboxEvent.reservation_id == rid))
        return json.dumps({'event_id': str(event.id), 'event_type': event.event_type, 'reservation_id': str(rid)})


def test_confirm_outbox_atomic_and_repeated_confirm(data):
    users, lab, seats, _ = data
    with pytest.raises(RuntimeError), Session.begin() as db:
        r, _ = svc.hold(db, users[0], lab, seats[0])
        svc.transition(db, users[0], r.id)
        db.flush()
        raise RuntimeError('rollback')
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        assert db.scalar(select(func.count()).select_from(Reservation)) == 0
    rid = confirmed(data)
    with Session.begin() as db:
        ticket = db.get(Reservation, rid).ticket_code
        assert svc.transition(db, users[0], rid).ticket_code == ticket
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_publisher_ambiguous_send_and_retry(data):
    rid = confirmed(data)
    queue = Queue(); queue.fail = True
    assert publish_batch(queue) == 0
    with Session.begin() as db:
        event = db.scalar(select(OutboxEvent))
        assert event.published_at is None and event.attempts == 1
        event.available_at = svc.now(db)
        assert db.get(Reservation, rid).status == 'CONFIRMED'
    queue.fail = False
    assert publish_batch(queue) == 1
    assert queue.messages[0] == queue.messages[1]
    assert set(json.loads(queue.messages[0])) == {'event_id', 'event_type', 'reservation_id'}
    assert publish_batch(queue) == 0


def test_publisher_commit_failure_redelivers(data):
    confirmed(data)
    queue = Queue()
    # Simulate process/connection death after successful SQS send before DB commit.
    class Crash:
        def __enter__(self):
            self.context = Session.begin(); return self.context.__enter__()
        def __exit__(self, *args):
            self.context.__exit__(RuntimeError, RuntimeError('crash'), None)
            raise RuntimeError('crash after publish')
    class Factory:
        def begin(self): return Crash()
    with pytest.raises(RuntimeError):
        publish_batch(queue, session_factory=Factory())
    assert publish_batch(queue) == 1
    assert queue.messages[0] == queue.messages[1]


def test_parallel_publishers_and_email_dedup(data):
    rid = confirmed(data); queue = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: publish_batch(queue), range(2))) == 1
    email = Email(); body = message(rid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        from app.modules.notifications.brevo import EmailProviderError
        def attempt(_):
            try: consume(body,email)
            except EmailProviderError: pass  # SQS retries in-progress claims.
        list(pool.map(attempt, range(2)))
    consume(body, email)
    assert email.calls == 1
    with Session() as db:
        delivery = db.get(NotificationDelivery, (rid, 'ReservationConfirmed'))
        assert delivery.status == 'SENT' and delivery.provider_message_id == 'mock-id'


def test_email_failure_does_not_change_reservation(data):
    rid = confirmed(data); email = Email(); email.fail = True
    with pytest.raises(RuntimeError): consume(message(rid), email)
    with Session() as db:
        assert db.get(Reservation, rid).status == 'CONFIRMED'
        assert db.get(NotificationDelivery, (rid, 'ReservationConfirmed')).status == 'PENDING'
    email.fail = False
    consume(message(rid), email)
    assert email.calls == 2


def test_worker_crash_after_provider_accept_can_duplicate(data):
    rid = confirmed(data)
    class CrashEmail(Email):
        def send(self, *args):
            super().send(*args)
            raise RuntimeError('process died after Brevo accepted')
    email = CrashEmail()
    with pytest.raises(RuntimeError): consume(message(rid), email)
    # No exactly-once claim: acceptance was not recorded, so the next attempt sends.
    retry = Email(); consume(message(rid), retry)
    assert email.calls == retry.calls == 1


@pytest.mark.parametrize('mode', ['missing', 'disabled', 'cancelled'])
def test_invalid_recipient_and_cancelled_registration(data, mode):
    rid = confirmed(data)
    if mode == 'missing':
        with Session.begin() as db: db.get(User,data[0][0]).email=''
    if mode == 'cancelled':
        with Session.begin() as db: svc.transition(db, data[0][0], rid, action='cancel')
    email = Email()
    consume(message(rid), None if mode == 'disabled' else email)
    assert email.calls == 0
    with Session() as db:
        assert db.get(NotificationDelivery, (rid, 'ReservationConfirmed')).status == 'SKIPPED'


def test_forged_or_poison_envelope_is_not_acknowledged(data):
    rid = confirmed(data)
    body = json.loads(message(rid)); body['event_id'] = '00000000-0000-0000-0000-000000000000'
    with pytest.raises(ValueError): consume(json.dumps(body), Email())
    with pytest.raises(ValueError): consume('{"recipient":"private"}', Email())
