"""B4 marker lifecycle and read-only evidence. DATABASE_URL stays in the environment."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

KIND = 'assessment_b4_marker'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def connect(expected_host):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['DATABASE_URL'])
    if url.host != expected_host:
        raise ValueError('Database host mismatch')
    if expected_host.endswith('.rds.amazonaws.com') and url.query.get('sslmode') != 'verify-full':
        raise ValueError('RDS connection must use sslmode=verify-full')
    return create_engine(url, pool_size=1, max_overflow=0, connect_args={
        'connect_timeout': 5, 'options': '-c timezone=UTC -c statement_timeout=20000 -c lock_timeout=5000'})


def identity(engine):
    # Same source identity check works when PITR uses a different database hostname.
    with engine.connect() as db:
        from sqlalchemy import text
        return str(db.execute(text('SELECT current_database()')).scalar_one())


def marker_once(engine, run_id, sequence):
    """Commit a non-publishable synthetic row; preserve DB-clock commit bounds."""
    from sqlalchemy import text
    marker_id = str(uuid.uuid5(run_id, f'marker-{sequence}'))
    with engine.begin() as db:
        row = db.execute(text('''INSERT INTO platform_events
            (id, kind, subject_id, created_at, published_at)
            SELECT :id, :kind, :run, clock_timestamp(), clock_timestamp()
            RETURNING created_at, xmin::text AS transaction_id'''),
            {'id': marker_id, 'kind': KIND, 'run': str(run_id)}).one()
    # COMMIT succeeded before this second DB-clock read. Do not call created_at an exact commit instant.
    with engine.connect() as db:
        upper = db.execute(text('SELECT clock_timestamp()')).scalar_one()
        tracking = db.execute(text('SHOW track_commit_timestamp')).scalar_one()
        exact = db.execute(text('SELECT pg_xact_commit_timestamp(CAST(:xid AS xid))'),
                           {'xid': row.transaction_id}).scalar_one() if tracking == 'on' else None
    return {'id': marker_id, 'sequence': sequence, 'commit_lower_bound': row.created_at.isoformat(),
            'commit_ack_upper_bound': upper.isoformat(), 'transaction_id': row.transaction_id,
            'exact_commit_at': exact.isoformat() if exact else None}


def verify_markers(engine, record, incident_at):
    from sqlalchemy import text
    incident = datetime.fromisoformat(incident_at.replace('Z', '+00:00'))
    if incident.tzinfo is None:
        raise ValueError('incident_at requires timezone')
    run_id = uuid.UUID(record['run_id'])
    found = []
    with engine.begin() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        for marker in record['markers']:
            if marker['id'] != str(uuid.uuid5(run_id, f"marker-{marker['sequence']}")):
                raise ValueError('Marker manifest ID mismatch')
            lower = datetime.fromisoformat(marker['commit_lower_bound'])
            upper = datetime.fromisoformat(marker['commit_ack_upper_bound'])
            if lower.tzinfo is None or upper.tzinfo is None or lower > upper:
                raise ValueError('Invalid DB-clock commit bounds')
            if marker.get('exact_commit_at'):
                exact = datetime.fromisoformat(marker['exact_commit_at'])
                if not lower <= exact <= upper:
                    raise ValueError('Exact commit time outside recorded bounds')
            row = db.execute(text('''SELECT created_at, published_at FROM platform_events
                WHERE id=:id AND subject_id=:run AND kind=:kind'''),
                {'id': marker['id'], 'run': str(run_id), 'kind': KIND}).first()
            if not row:
                continue
            if row.created_at.isoformat() != marker['commit_lower_bound'] or row.published_at is None:
                raise ValueError('Recovered marker differs from committed source record')
            if datetime.fromisoformat(marker['commit_ack_upper_bound']) <= incident:
                found.append(marker)
    latest = max(found, key=lambda x: x['commit_lower_bound']) if found else None
    return {'recovered_markers': len(found), 'latest_recovered_marker': latest,
            'incident_at': incident.isoformat(),
            'rpo_upper_bound_seconds': (incident - datetime.fromisoformat(latest['commit_lower_bound'])).total_seconds() if latest else None,
            'rpo_exact_seconds': (incident - datetime.fromisoformat(latest['exact_commit_at'])).total_seconds()
                                 if latest and latest.get('exact_commit_at') else None,
            'note': 'Conservative RPO bound from a durable marker; exact time only when PostgreSQL commit tracking supplied it. Never enable tracking on the source just for this script.'}


def snapshot(engine, scope):
    from sqlalchemy import text, bindparam
    # Never export profile values, passwords, ticket codes or raw rows.
    fields = {
        'users': 'id,role,status',
        'events': 'id,status,poster_key',
        'rooms': 'id,image_key',
        'seats': 'id,room_id,capacity',
        'lab_sessions': 'id,event_id,room_id,open_at,close_at,start_at,end_at,checkin_enabled',
        'reservations': 'id,user_id,session_id,seat_id,slot,status,hold_expires_at,checked_in_at,ticket_code',
    }
    if set(scope) != set(fields):
        raise ValueError('Scope must specify all six tables explicitly')
    ids = {table: [str(uuid.UUID(x)) for x in values] for table, values in scope.items()}
    if any(not values or len(values) > 2000 for values in ids.values()):
        raise ValueError('Each scope needs 1..2000 synthetic IDs')
    source = Path(__file__).resolve().parents[3] / 'scripts/tests/db-invariants.sql'
    statements = [s.strip() for s in '\n'.join(line for line in source.read_text().splitlines()
                  if not line.lstrip().startswith('--')).split(';') if s.strip()]
    queries = [s for s in statements if s.upper().startswith('SELECT')]
    if len(queries) != 7:
        raise ValueError('Review updated invariant SQL before execution')
    with engine.begin() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        result = {'db_clock': db.execute(text('SELECT clock_timestamp()')).scalar_one().isoformat(),
                  'schema_revision': db.execute(text('SELECT version_num FROM alembic_version')).scalar_one(),
                  'invariant_violations': [len(db.execute(text(q)).fetchall()) for q in queries], 'tables': {}}
        result['unvalidated_constraints'] = db.execute(text("SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='public' AND NOT c.convalidated")).scalar_one()
        for table, columns in fields.items():
            query = text(f'SELECT {columns} FROM {table} WHERE id IN :ids ORDER BY id').bindparams(bindparam('ids', expanding=True))
            rows = [dict(row) for row in db.execute(query, {'ids': ids[table]}).mappings()]
            canonical = json.dumps(rows, sort_keys=True, default=str, separators=(',', ':')).encode()
            result['tables'][table] = {'expected_count': len(set(ids[table])), 'count': len(rows),
                                       'sha256': hashlib.sha256(canonical).hexdigest()}
        query = text('''SELECT count(*) FROM reservations r
            LEFT JOIN users u ON u.id=r.user_id LEFT JOIN lab_sessions l ON l.id=r.session_id
            LEFT JOIN seats s ON s.id=r.seat_id
            WHERE r.id IN :ids AND (u.id IS NULL OR l.id IS NULL OR s.id IS NULL OR l.room_id <> s.room_id)''').bindparams(bindparam('ids', expanding=True))
        result['ownership_violations'] = db.execute(query, {'ids': ids['reservations']}).scalar_one()
    result['passed'] = (not any(result['invariant_violations']) and result['unvalidated_constraints'] == 0
                        and result['ownership_violations'] == 0
                        and all(x['count'] == x['expected_count'] for x in result['tables'].values()))
    result['hash_scope'] = 'Explicit synthetic IDs, structural fields and ticket_code hashed in memory; no raw rows/ticket payload exported; not a full database/profile hash'
    return result


def cleanup_markers(engine, record):
    from sqlalchemy import text
    run_id = uuid.UUID(record['run_id'])
    with engine.begin() as db:
        count = 0
        planned = record.get('planned_marker_ids', [m['id'] for m in record['markers']])
        if len(planned) != len(set(planned)) or any(
                value != str(uuid.uuid5(run_id, f'marker-{index}')) for index, value in enumerate(planned)):
            raise ValueError('Invalid planned marker identities')
        known = {m['id']: m for m in record['markers']}
        for marker_id in planned:
            marker = known.get(marker_id)
            if marker is None:
                # Planned IDs are persisted before writes, covering a crash after COMMIT but before file save.
                count += db.execute(text('''DELETE FROM platform_events
                    WHERE id=:id AND kind=:kind AND subject_id=:run AND published_at IS NOT NULL'''),
                    {'id': marker_id, 'run': str(run_id), 'kind': KIND}).rowcount
                continue
            if marker['id'] != str(uuid.uuid5(run_id, f"marker-{marker['sequence']}")):
                raise ValueError('Marker manifest ID mismatch; transaction rolled back')
            count += db.execute(text('''DELETE FROM platform_events
                WHERE id=:id AND kind=:kind AND subject_id=:run AND published_at IS NOT NULL
                AND created_at=:created'''), {'id': marker['id'], 'run': str(run_id), 'kind': KIND,
                                              'created': datetime.fromisoformat(marker['commit_lower_bound'])}).rowcount
    return {'deleted_marker_rows': count, 'run_id': str(run_id)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['markers', 'verify-markers', 'snapshot', 'cleanup-markers'])
    parser.add_argument('--expected-host', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--record', type=Path)
    parser.add_argument('--scope', type=Path)
    parser.add_argument('--incident-at')
    parser.add_argument('--run-id', type=uuid.UUID)
    parser.add_argument('--samples', type=int, default=3)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.action in ('markers', 'cleanup-markers') and not args.execute:
        print('Plan only: no database connection or write; add --execute after the B4 window handoff')
        return
    engine = connect(args.expected_host)
    try:
        if args.action == 'markers':
            if not args.run_id or not 2 <= args.samples <= 60 or args.interval < 60:
                raise ValueError('Require run UUID, 2..60 samples and interval >=60s')
            if args.output.exists():
                raise ValueError('Refuse to overwrite a marker manifest')
            result = {'run_id': str(args.run_id), 'database': identity(engine), 'markers': [],
                      'planned_marker_ids': [str(uuid.uuid5(args.run_id, f'marker-{i}')) for i in range(args.samples)]}
            write_json(args.output, result)
            for sequence in range(args.samples):
                result['markers'].append(marker_once(engine, args.run_id, sequence))
                write_json(args.output, result)
                if sequence + 1 < args.samples:
                    time.sleep(args.interval)
        elif args.action == 'snapshot':
            result = snapshot(engine, json.loads(args.scope.read_text(encoding='utf-8-sig')))
            write_json(args.output, result)
            if not result['passed']:
                raise SystemExit(1)
        else:
            record = json.loads(args.record.read_text(encoding='utf-8-sig'))
            if identity(engine) != record['database']:
                raise ValueError('Database name differs from marker manifest')
            result = (verify_markers(engine, record, args.incident_at) if args.action == 'verify-markers'
                      else cleanup_markers(engine, record))
            write_json(args.output, result)
        print('B4 result saved; no raw database rows or credentials printed')
    finally:
        engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(f'B4 operation failed ({type(exc).__name__}); inspect privately without publishing credentials') from None
