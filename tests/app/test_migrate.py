"""Frozen baseline, guarded revision adoption and atomic data preservation."""

import os
import pytest

URL = os.getenv("TEST_DATABASE_URL")
if not URL:
    pytest.skip("Disposable PostgreSQL required", allow_module_level=True)
if os.getenv("APP_ENV") != "test" or not URL.rsplit("/", 1)[-1].endswith("_test"):
    raise RuntimeError("Use a disposable *_test database")
os.environ["DATABASE_URL"] = URL
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text, inspect
from sqlalchemy.exc import ProgrammingError
from app.infrastructure.database.session import engine, Base, Session
from app import models as m
from app.migrate import upgrade, HEAD, BASELINE, MATCHING_SCHEMA_REVISION


@pytest.fixture(autouse=True)
def reset():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def current():
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_heads()


def snapshot(template=None):
    # Test-only full rows; never run this helper against the serving database.
    with engine.connect() as conn:
        rows = {
            table: conn.execute(
                text(f'SELECT to_jsonb(t) FROM "{table}" t ORDER BY to_jsonb(t)::text')
            )
            .scalars()
            .all()
            for table in sorted(inspect(engine).get_table_names()) if table != "alembic_version"
        }
        if template is not None:
            return {table:[{key:row[key] for key in template[table][0]} for row in rows[table]] if template[table] else rows[table] for table in template}
        return rows


def matching_database():
    from datetime import datetime, timedelta, timezone
    import uuid

    upgrade()
    now = datetime.now(timezone.utc)
    with Session.begin() as db:
        user = m.User(
            username="keep-user",
            password_hash="fixture-hash",
            role="admin",
            full_name="Fixture Name",
            cccd="012345678901",
            email="fixture@example.test",
            phone="",
            avatar_key="users/fixture/avatars/fixture.jpg",
        )
        room = m.Room(name="keep-room", image_key="rooms/fixture.jpg")
        event = m.Event(
            name="keep-session",
            session_type="exam",
            description="keep-description",
            venue="keep-venue",
            address="keep-address",
            poster_key="events/fixture/poster/fixture.jpg",
        )
        db.add_all([user, room, event])
        db.flush()
        seat = m.Seat(room_id=room.id, seat_code="A101", capacity=30)
        lab = m.LabSession(
            room_id=room.id,
            event_id=event.id,
            checkin_enabled=True,
            open_at=now - timedelta(hours=2),
            close_at=now - timedelta(hours=1),
            start_at=now,
            end_at=now + timedelta(hours=1),
        )
        db.add_all([seat, lab])
        db.flush()
        db.add(m.SessionSeat(session_id=lab.id, seat_id=seat.id))
        db.flush()
        registration = m.Reservation(
            user_id=user.id,
            session_id=lab.id,
            seat_id=seat.id,
            slot=7,
            status="CHECKED_IN",
            ticket_code="fixture-stable-ticket-code",
            hold_expires_at=now - timedelta(hours=1),
            checked_in_at=now,
        )
        db.add(registration)
        db.flush()
        db.add_all(
            [
                m.LoginSession(
                    user_id=user.id,
                    token_hash="a" * 64,
                    csrf_hash="b" * 64,
                    expires_at=now + timedelta(hours=8),
                ),
                m.RoomLayout(
                    room_id=room.id,
                    revision=8,
                    layout={
                        "type": "image",
                        "elements": [],
                        "image_key": "rooms/fixture/maps/fixture.png",
                    },
                ),
                m.AuditEvent(
                    actor_id=user.id,
                    reservation_id=registration.id,
                    action="CHECKED_IN",
                ),
                m.CheckinPolicyEvent(actor_id=user.id, session_id=lab.id, enabled=True),
                m.OutboxEvent(
                    reservation_id=registration.id,
                    event_type="ReservationConfirmed",
                    published_at=now,
                    attempts=3,
                ),
                m.NotificationDelivery(
                    reservation_id=registration.id,
                    notification_type="ReservationConfirmed",
                    status="SENT",
                    provider_message_id="fixture-accepted",
                    completed_at=now,
                ),
                m.IdempotencyRecord(
                    user_id=user.id,
                    key_hash="c" * 64,
                    fingerprint="d" * 64,
                    response={"hold_id": str(registration.id)},
                ),
                m.QueuePolicyEvent(
                    actor="fixture-operator",
                    reason="fixture",
                    before={"enabled": False},
                    after={"enabled": True},
                ),
            ]
        )
        policy = db.get(m.QueueSettings, 1)
        policy.enabled = True
        policy.capacity = 33
        policy.policy_version = 7
        policy.epoch = uuid.uuid4()
    command.downgrade(Config("migrations/alembic.ini"),BASELINE)
    with engine.begin() as db:
        db.execute(
            text("UPDATE alembic_version SET version_num=:revision"),
            {"revision": MATCHING_SCHEMA_REVISION},
        )
    return snapshot()


def test_single_frozen_baseline_and_fresh_roundtrip():
    script = ScriptDirectory.from_config(Config("migrations/alembic.ini"))
    assert [revision.revision for revision in script.walk_revisions()] == [HEAD, BASELINE]
    upgrade()
    upgrade()
    assert current() == (HEAD,)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        assert conn.execute(
            text("SELECT capacity,enabled FROM booking_queue_settings")
        ).one() == (10, False)
    command.downgrade(Config("migrations/alembic.ini"), "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    upgrade()
    assert current() == (HEAD,)


def test_adoption_changes_only_revision_and_preserves_every_business_table():
    before = matching_database()
    upgrade()
    upgrade()
    assert current() == (HEAD,)
    assert snapshot(before) == before


@pytest.mark.parametrize(
    "ddl",
    [
        "ALTER TABLE rooms ADD COLUMN unexpected text",
        "ALTER TABLE users ALTER COLUMN email DROP DEFAULT",
        "ALTER TABLE users ALTER COLUMN username TYPE varchar(99)",
        "ALTER TABLE seats DROP CONSTRAINT seat_capacity_range",
        "ALTER TABLE seats DROP CONSTRAINT seats_room_id_fkey",
        "DROP INDEX uq_active_seat_session",
        "DROP INDEX uq_active_user_session; CREATE UNIQUE INDEX uq_active_user_session ON reservations (user_id,session_id) WHERE status='CONFIRMED'",
        "ALTER TABLE seats DROP CONSTRAINT seat_capacity_range; ALTER TABLE seats ADD CONSTRAINT seat_capacity_range CHECK (capacity >= 1)",
    ],
)
def test_drift_refuses_adoption_without_modifying_revision_or_rows(ddl):
    matching_database()
    with engine.begin() as conn:
        conn.execute(text(ddl))
    before = snapshot()
    with pytest.raises(RuntimeError, match="differs"):
        upgrade()
    assert current() == (MATCHING_SCHEMA_REVISION,)
    assert snapshot(before) == before


def test_missing_queue_policy_refuses_adoption():
    matching_database()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM booking_queue_settings"))
    with pytest.raises(RuntimeError, match="policy is missing"):
        upgrade()
    assert current() == (MATCHING_SCHEMA_REVISION,)


def test_unknown_revision_is_untouched():
    upgrade()
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='unknown_revision'"))
    with pytest.raises(RuntimeError, match="Unknown"):
        upgrade()
    assert current() == ("unknown_revision",)


def test_unversioned_existing_tables_are_not_automatically_stamped():
    upgrade()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM alembic_version"))
    before = snapshot()
    with pytest.raises(ProgrammingError):
        upgrade()
    assert current() == ()
    assert snapshot(before) == before


@pytest.mark.parametrize("adopt", [False, True])
def test_concurrent_migration_processes_are_serialized(adopt):
    from concurrent.futures import ThreadPoolExecutor
    import subprocess, sys

    before = matching_database() if adopt else None

    def migrate():
        return subprocess.run(
            [sys.executable, "-m", "app.migrate"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: migrate(), range(3)))
    assert all(result.returncode == 0 for result in results), [
        r.stderr for r in results
    ]
    assert current() == (HEAD,)
    if before is not None:
        assert snapshot(before) == before
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_release_smoke_accepts_future_additive_schema_for_rollback():
    upgrade()
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE outbox_events ADD COLUMN future_nullable_field text")
        )
        conn.execute(text("UPDATE alembic_version SET version_num='future_fixture'"))
    from app.smoke import main

    main()


@pytest.mark.parametrize('column,value',[('email','same@example.test'),('cccd','012345678901')])
def test_duplicate_identity_preflight_is_atomic(column,value):
    command.upgrade(Config('migrations/alembic.ini'),BASELINE)
    import uuid
    with engine.begin() as db:
        for i in range(2):
            db.execute(text(f'INSERT INTO users(id,username,password_hash,role,{column}) VALUES (:id,:name,:password,:role,:value)'),
                {'id':uuid.uuid4(),'name':f'duplicate-{i}','password':'fixture','role':'student','value':value.upper() if column=='email' and i else value})
    before=snapshot()
    with pytest.raises(RuntimeError,match='Duplicate'):upgrade()
    assert current()==(BASELINE,)
    assert snapshot()==before


def test_release_smoke_refuses_missing_platform_schema():
    upgrade()
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE email_jobs CASCADE'))
    from app.smoke import main
    with pytest.raises(ProgrammingError):main()
