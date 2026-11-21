"""Backup/cleanup safety checks, restricted to the restored disposable database."""
import os
from datetime import timedelta
from uuid import uuid4
from pathlib import Path
from collections import Counter
from copy import deepcopy

import pytest

if (os.getenv('APP_ENV') != 'test'
        or os.getenv('DATABASE_URL') != os.getenv('TEST_DATABASE_URL')
        or not os.getenv('DATABASE_URL', '').endswith('_test')):
    pytest.skip('Explicit disposable database required', allow_module_level=True)

from demo_backup import canonical_constraint, fingerprint
from isolated_load import Scope, cleanup, manifest, prepare, sessions, physics_map, PHYSICS_ROOM, mechanic_map, MECHANIC_ROOM, MECHANIC_EVENT
from app.infrastructure.database.session import Session
from app.models import LabSession, RoomLayout, Reservation
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


@pytest.mark.skipif(not os.getenv('ASSESSMENT_MECHANIC_IMAGE'), reason='Restored Mechanic source assets required')
def test_mechanic_clone_sessions_cleanup_preserve_demo(tmp_path):
    from app.infrastructure.storage.objects import storage
    from app.models import Event, Seat
    from sqlalchemy import select
    with Session() as db:
        assert db.get_bind().url.host=='backup-verify-db'
        original=fingerprint(db.connection().connection.driver_connection,business=True)
        source=db.get(RoomLayout,MECHANIC_ROOM);source_event=db.get(Event,MECHANIC_EVENT)
        before=deepcopy(source.layout);name=source_event.name;status=source_event.status
        storage().put(source.layout['image_key'],Path(os.environ['ASSESSMENT_MECHANIC_IMAGE']).read_bytes(),'image/png')
        storage().put(source_event.poster_key,Path(os.environ['ASSESSMENT_MECHANIC_POSTER']).read_bytes(),'image/jpeg')
        scope=Scope('demo-load-mechanic-test');prepare(db,scope,'disposable-only-master',now(db)+timedelta(days=2))
        row=Reservation(user_id=scope.users[0],session_id=scope.lab,seat_id=scope.seats[0],status='HELD',hold_expires_at=now(db)+timedelta(minutes=3))
        db.add(row);db.flush()
        with pytest.raises(RuntimeError,match='no live or foreign'):mechanic_map(db,scope,tmp_path)
        row.status='CANCELLED';db.flush()
        result=mechanic_map(db,scope,tmp_path)
        assert result['capacity']==180 and result['source_capacity']==68
        assert source.layout==before and source_event.name==name and source_event.status==status
        assert all(s.capacity==17 for s in db.scalars(select(Seat).where(Seat.room_id==MECHANIC_ROOM)))
        rev=db.get(RoomLayout,scope.room).revision
        assert mechanic_map(db,scope,tmp_path)['unchanged'] and db.get(RoomLayout,scope.room).revision==rev
        package,identities=sessions(db,scope,14400)
        assert len(identities)==100 and package['capacity']==180 and len(package['seats'])==4
        assert len({s['session_token'] for s in identities})==100
        assert len({s['csrf_token'] for s in identities})==100
        assert sorted(Counter(s['seat_id'] for s in identities).values())==[25]*4
        assert all(s['seat_id']==package['mapping'][i]['seat_id'] for i,s in enumerate(identities))
        cleanup(db,scope,execute=True)
        after=fingerprint(db.connection().connection.driver_connection,business=True)
        assert after['tables']==original['tables'] and after['invariant_rows']==[0]*7
        db.rollback()


@pytest.mark.skipif(not os.getenv('ASSESSMENT_PHYSICS_IMAGE'), reason='Restored Physics source image required')
def test_physics_clone_preserves_history_source_and_shared_room_mapping(tmp_path):
    from app.infrastructure.storage.objects import storage
    with Session() as db:
        assert db.get_bind().url.host == 'backup-verify-db'
        source=db.get(RoomLayout, PHYSICS_ROOM)
        assert source is not None
        original=deepcopy(source.layout)
        storage().put(source.layout['image_key'], Path(os.environ['ASSESSMENT_PHYSICS_IMAGE']).read_bytes(), 'image/png')
        scope=Scope('demo-load-physics-test')
        prepare(db, scope, 'disposable-only-master', now(db)+timedelta(days=1))
        row=Reservation(user_id=scope.users[0], session_id=scope.lab,seat_id=scope.seats[0],
                        status='CANCELLED',hold_expires_at=now(db)+timedelta(minutes=3))
        db.add(row);db.flush();reservation_id=row.id
        with db.begin_nested() as savepoint:
            row.status='HELD';db.flush()
            with pytest.raises(RuntimeError,match='no live or foreign'):
                physics_map(db,scope,tmp_path)
            savepoint.rollback()
        result=physics_map(db,scope,tmp_path)
        assert result['zones']==34 and result['capacity']==1530
        assert result['preserved_cancelled_reservations']==1
        assert db.get(Reservation,reservation_id).status=='CANCELLED'
        assert source.layout==original
        revision=db.get(RoomLayout,scope.room).revision
        assert physics_map(db,scope,tmp_path)['unchanged']
        assert db.get(RoomLayout,scope.room).revision==revision
        package,identities=sessions(db,scope,14400)
        assert package['capacity']==1530 and len(package['seats'])==34
        assert len({x['session_token'] for x in identities})==100
        assert len({x['csrf_token'] for x in identities})==100
        assigned=Counter(x['seat_id'] for x in identities)
        assert len(assigned)==34 and max(assigned.values())==3
        assert all(x['seat_id']==package['mapping'][i]['seat_id'] for i,x in enumerate(identities))
        assert fingerprint(db.connection().connection.driver_connection)['invariant_rows']==[0]*7
        cleanup(db,scope,execute=True)
        assert source.layout==original
        db.rollback()
