"""Backup/cleanup safety checks, restricted to the restored disposable database."""
import os
from datetime import timedelta
from uuid import uuid4

import pytest

if (os.getenv('APP_ENV') != 'test'
        or os.getenv('DATABASE_URL') != os.getenv('TEST_DATABASE_URL')
        or not os.getenv('DATABASE_URL', '').endswith('_test')):
    pytest.skip('Explicit disposable database required', allow_module_level=True)

from demo_backup import canonical_constraint, fingerprint
from isolated_load import Scope, cleanup, manifest, prepare, sessions
from app.infrastructure.database.session import Session
from app.models import LabSession
from app.modules.booking.service import now


def test_constraint_normalization_preserves_semantics():
    source = "CHECK (((role)::text = ANY ((ARRAY['admin'::character varying, 'student'::character varying])::text[])))"
    restored = "CHECK (((role)::text = ANY (ARRAY[('admin'::character varying)::text, ('student'::character varying)::text])))"
    normalize = lambda value: canonical_constraint('users', 'users_role_check', value)
    assert normalize(source) == normalize(restored)
    assert normalize(source) != normalize(restored.replace('student', 'staff'))
    for changed in (restored.replace(' = ', ' <> '), restored + ' OR true', restored.replace('role', 'status')):
        assert normalize(changed) == changed
    assert canonical_constraint('other', 'users_role_check', source) == source


def test_fixture_session_and_foreign_reference_cleanup_guards():
    with Session() as db:
        assert db.get_bind().url.host == 'backup-verify-db'
        original = fingerprint(db.connection().connection.driver_connection)
        scope = Scope('demo-load-safety-test')
        prepare(db, scope, 'disposable-only-master', now(db) + timedelta(days=1))
        first = manifest(db, scope)
        prepare(db, scope, 'disposable-only-master', now(db) + timedelta(days=1))
        assert manifest(db, scope) == first
        package, identities = sessions(db, scope, 14400)
        assert len(identities) == 100 and package['capacity'] == 120
        assert len(package['mapping']) == 100
        assert package['mapping'][0]['seat_id'] == identities[0]['seat_id']
        for field in ('session_token', 'csrf_token', 'seat_id'):
            assert len({item[field] for item in identities}) == 100
        assert cleanup(db, scope)['before'] == dict(users=100, events=1, schedules=1, seats=120, reservations=0)
        with db.begin_nested() as savepoint:
            own = db.get(LabSession, scope.lab)
            db.add(LabSession(id=uuid4(), event_id=own.event_id, room_id=own.room_id,
                             open_at=own.open_at, close_at=own.close_at,
                             start_at=own.start_at, end_at=own.end_at, checkin_enabled=False))
            db.flush()
            with pytest.raises(RuntimeError, match='foreign schedule'):
                cleanup(db, scope, execute=True)
            savepoint.rollback()
        cleanup(db, scope, execute=True)
        assert not any(cleanup(db, scope, execute=True)['before'].values())
        after = fingerprint(db.connection().connection.driver_connection)
        assert after['tables'] == original['tables']
        assert after['constraints_sha256'] == original['constraints_sha256']
        assert after['invariant_rows'] == [0] * 7
        db.rollback()
