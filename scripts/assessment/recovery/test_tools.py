"""B4 guard tests and opt-in integration on a dedicated disposable PostgreSQL."""
import importlib.util
import json
import os
from pathlib import Path
import uuid
import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load('db_checks')
plan = load('app_plan')
restore_plan = load('restore_plan')


def source_and_config():
    source = {'taskRoleArn': 'source-role', 'executionRoleArn': 'source-execution',
              'containerDefinitions': [{'name': 'app', 'image': 'example/app@sha256:' + 'a' * 64,
                  'memoryReservation': 256, 'environment': [{'name': 'SQS_QUEUE_URL', 'value': 'production-queue'}],
                  'secrets': [{'name': 'BREVO_API_KEY', 'valueFrom': 'source-secret'}],
                  'command': ['python', '-m', 'app.worker']}, {'name': 'sidecar', 'image': 'ignored'}]}
    config = {'family': 'labseat-b4-fixture', 'run_id': str(uuid.uuid4()), 'taskRoleArn': 'recovery-role',
              'executionRoleArn': 'recovery-execution', 'region': 'ap-southeast-2',
              'cluster': 'test-cluster', 'bucket': 'test-bucket', 'prefix': 'assessment/b4/fixture/',
              'subnets': ['subnet-private'], 'security_groups': ['sg-private'],
              'secrets': {k: 'arn:aws:ssm:ap-southeast-2:000000000000:parameter/b4/' + k for k in
                          ['DATABASE_URL', 'REDIS_URL', 'REDIS_USERNAME', 'REDIS_PASSWORD', 'REDIS_CA_CERT']}}
    return source, config


def test_app_plan_drops_background_and_production_settings():
    source, config = source_and_config()
    result = plan.build(source, config)
    containers = result['register_task_input']['containerDefinitions']
    assert len(containers) == 1
    assert containers[0]['entryPoint'] == ['python']
    assert 'app.main:app' in containers[0]['command']
    assert 'SQS_QUEUE_URL' not in json.dumps(result)
    assert 'BREVO_API_KEY' not in json.dumps(result)
    assert 'production-queue' not in json.dumps(result)
    assert result['run_task_input']['networkConfiguration']['awsvpcConfiguration']['assignPublicIp'] == 'DISABLED'
    assert containers[0]['image'] == source['containerDefinitions'][0]['image']
    assert result['register_task_input']['tags'][1]['value'] == config['run_id']


@pytest.mark.parametrize('change', ['mutable-image', 'source-role', 'source-secret', 'plaintext-secret',
                                    'duplicate-secret', 'shared-prefix', 'extra-secret', 'wrong-family'])
def test_app_plan_rejects_unsafe_inputs(change):
    source, config = source_and_config()
    if change == 'mutable-image': source['containerDefinitions'][0]['image'] = 'app:latest'
    if change == 'source-role': config['taskRoleArn'] = source['taskRoleArn']
    if change == 'source-secret': config['secrets']['DATABASE_URL'] = 'source-secret'
    if change == 'plaintext-secret': config['secrets']['DATABASE_URL'] = 'postgresql://secret'
    if change == 'duplicate-secret': config['secrets']['DATABASE_URL'] = config['secrets']['REDIS_URL']
    if change == 'shared-prefix': config['prefix'] = 'production/'
    if change == 'extra-secret': config['secrets']['BREVO_API_KEY'] = 'unexpected'
    if change == 'wrong-family': config['family'] = 'labseat-lab-api'
    with pytest.raises(ValueError): plan.build(source, config)


def test_db_host_and_tls_guards(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@test-db/b4_tools_test')
    with pytest.raises(ValueError): checks.connect('wrong-host')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@fixture.rds.amazonaws.com/test')
    with pytest.raises(ValueError): checks.connect('fixture.rds.amazonaws.com')


def restore_source_and_config():
    return ({'DBInstanceIdentifier': 'labseat-lab', 'Engine': 'postgres', 'StorageEncrypted': True,
             'PubliclyAccessible': False, 'DBInstanceClass': 'db.t4g.micro', 'StorageType': 'gp3',
             'LatestRestorableTime': '2026-11-19T04:00:00Z', 'Endpoint': {'Port': 5432},
             'DBSubnetGroup': {'DBSubnetGroupName': 'private'},
             'DBParameterGroups': [{'DBParameterGroupName': 'source-parameters'}],
             'VpcSecurityGroups': [{'VpcSecurityGroupId': 'sg-source'}]},
            {'run_id': str(uuid.uuid4()), 'target_db': 'labseat-b4-fixture', 'owner': 'fixture',
             'incident_at': '2026-11-19T04:01:00Z', 'restore_time': '2026-11-19T03:59:00Z',
             'earliest_restorable_time': '2026-11-18T04:00:00Z',
             'security_groups': ['sg-recovery'], 'multi_az': False})


def test_restore_plan_preserves_source_and_requires_private_target():
    source, config = restore_source_and_config()
    before = json.dumps(source, sort_keys=True)
    result = restore_plan.build(source, config)
    assert result['status'] == 'PLAN_ONLY'
    assert result['restore_input']['PubliclyAccessible'] is False
    assert result['restore_input']['SourceDBInstanceIdentifier'] != result['restore_input']['TargetDBInstanceIdentifier']
    assert result['restore_input']['RestoreTime'] == '2026-11-19T03:59:00+00:00'
    assert result['cleanup_identity']['required_tags']['run'] == config['run_id']
    assert before == json.dumps(source, sort_keys=True)


@pytest.mark.parametrize('change', ['source-target', 'too-late', 'too-early', 'after-incident',
                                   'no-timezone', 'shared-sg', 'public', 'unencrypted', 'cluster'])
def test_restore_plan_rejects_wrong_target_and_time(change):
    source, config = restore_source_and_config()
    if change == 'source-target': config['target_db'] = source['DBInstanceIdentifier']
    if change == 'too-late': config['restore_time'] = '2026-11-19T04:02:00Z'
    if change == 'too-early': config['restore_time'] = '2026-11-17T04:00:00Z'
    if change == 'after-incident': config['incident_at'] = '2026-11-19T03:58:00Z'
    if change == 'no-timezone': config['restore_time'] = '2026-11-19T03:59:00'
    if change == 'shared-sg': config['security_groups'] = ['sg-source']
    if change == 'public': source['PubliclyAccessible'] = True
    if change == 'unencrypted': source['StorageEncrypted'] = False
    if change == 'cluster': source['DBClusterIdentifier'] = 'wrong-api'
    with pytest.raises(ValueError): restore_plan.build(source, config)


@pytest.mark.parametrize('change', ['valid', 'wrong-id', 'source-id', 'wrong-run', 'protected'])
def test_cloud_cleanup_guard(change):
    source, config = restore_source_and_config()
    request = restore_plan.build(source, config)
    state = {'DBInstanceIdentifier': config['target_db'], 'DeletionProtection': False,
             'TagList': request['restore_input']['Tags']}
    if change == 'wrong-id': state['DBInstanceIdentifier'] = 'labseat-b4-another'
    if change == 'source-id': state['DBInstanceIdentifier'] = source['DBInstanceIdentifier']
    if change == 'wrong-run': state['TagList'] = [{'Key': 'run', 'Value': str(uuid.uuid4())}]
    if change == 'protected': state['DeletionProtection'] = True
    if change == 'valid':
        result = restore_plan.cleanup_plan(state, request)
        assert result['status'] == 'PLAN_ONLY'
        assert result['delete_db_input']['DBInstanceIdentifier'] == config['target_db']
    else:
        with pytest.raises(ValueError): restore_plan.cleanup_plan(state, request)


@pytest.fixture
def database(monkeypatch):
    from sqlalchemy.engine import make_url
    url = os.getenv('B4_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Opt-in disposable B4_TEST_DATABASE_URL required')
    target = make_url(url)
    assert target.host == 'test-db' and target.database == 'b4_tools_test'
    monkeypatch.setenv('DATABASE_URL', url)
    engine = checks.connect('test-db')
    yield engine
    engine.dispose()


def test_markers_are_committed_and_cleanup_is_scoped(database):
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text
    run_id, other = uuid.uuid4(), uuid.uuid4()
    marker = checks.marker_once(database, run_id, 0)
    neighbour = checks.marker_once(database, other, 0)
    record = {'run_id': str(run_id), 'markers': [marker]}
    result = checks.verify_markers(database, record, (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat())
    assert result['recovered_markers'] == 1 and result['rpo_upper_bound_seconds'] >= 0
    if marker['exact_commit_at']:
        assert 0 <= result['rpo_exact_seconds'] <= result['rpo_upper_bound_seconds']
    else:
        assert result['rpo_exact_seconds'] is None
    assert checks.cleanup_markers(database, record)['deleted_marker_rows'] == 1
    assert checks.cleanup_markers(database, record)['deleted_marker_rows'] == 0
    with database.connect() as db:
        assert db.execute(text('SELECT count(*) FROM platform_events WHERE id=:id'), {'id': neighbour['id']}).scalar_one() == 1
    checks.cleanup_markers(database, {'run_id': str(other), 'markers': [neighbour]})


def test_marker_cleanup_recovers_commit_before_manifest_save(database):
    run_id = uuid.uuid4()
    marker = checks.marker_once(database, run_id, 0)
    record = {'run_id': str(run_id), 'markers': [], 'planned_marker_ids': [marker['id']]}
    assert checks.cleanup_markers(database, record)['deleted_marker_rows'] == 1


def test_marker_manifest_tampering_is_rejected(database):
    run_id = uuid.uuid4()
    marker = checks.marker_once(database, run_id, 0)
    bad = dict(marker, id=str(uuid.uuid4()))
    with pytest.raises(ValueError): checks.cleanup_markers(database, {'run_id': str(run_id), 'markers': [bad]})
    with pytest.raises(ValueError): checks.verify_markers(database, {'run_id': str(run_id), 'markers': [bad]}, '2026-12-01T00:00:00Z')
    assert checks.cleanup_markers(database, {'run_id': str(run_id), 'markers': [marker]})['deleted_marker_rows'] == 1


def test_snapshot_hashes_and_detects_invalid_capacity(database):
    from datetime import datetime, timezone, timedelta
    from sqlalchemy.orm import Session
    from sqlalchemy import text
    from app.models import User, Event, Room, Seat, LabSession, SessionSeat, Reservation
    now = datetime.now(timezone.utc)
    with Session(database) as db, db.begin():
        user = User(username='b4-' + uuid.uuid4().hex, password_hash='synthetic', role='student')
        event = Event(name='Synthetic B4 test')
        room = Room(name='Synthetic B4 room')
        db.add_all([user, event, room]); db.flush()
        seat = Seat(room_id=room.id, seat_code='fixture', capacity=2)
        lab = LabSession(event_id=event.id, room_id=room.id, open_at=now-timedelta(hours=2),
                         close_at=now+timedelta(hours=1), start_at=now+timedelta(hours=2), end_at=now+timedelta(hours=3))
        db.add_all([seat, lab]); db.flush()
        db.add(SessionSeat(session_id=lab.id, seat_id=seat.id)); db.flush()
        reservation = Reservation(user_id=user.id, session_id=lab.id, seat_id=seat.id,
                                  status='CONFIRMED', slot=0, ticket_code='synthetic-' + uuid.uuid4().hex,
                                  hold_expires_at=now+timedelta(minutes=5))
        db.add(reservation); db.flush()
        scope = {k: [str(v.id)] for k, v in {'users': user, 'events': event, 'rooms': room,
                 'seats': seat, 'lab_sessions': lab, 'reservations': reservation}.items()}
    try:
        first = checks.snapshot(database, scope)
        assert first['passed'] and first['tables'] == checks.snapshot(database, scope)['tables']
        with database.begin() as db:
            db.execute(text('UPDATE reservations SET slot=99 WHERE id=:id'), {'id': scope['reservations'][0]})
        invalid = checks.snapshot(database, scope)
        assert not invalid['passed'] and invalid['invariant_violations'][2] == 1
        assert first['tables']['reservations']['sha256'] != invalid['tables']['reservations']['sha256']
        missing = dict(scope, reservations=[str(uuid.uuid4())])
        assert not checks.snapshot(database, missing)['passed']
    finally:
        with database.begin() as db:
            for table in ['reservations', 'session_seats', 'lab_sessions', 'seats', 'rooms', 'events', 'users']:
                column, value = ('session_id', scope['lab_sessions'][0]) if table == 'session_seats' else ('id', scope[table][0])
                db.execute(text(f'DELETE FROM {table} WHERE {column}=:id'), {'id': value})
