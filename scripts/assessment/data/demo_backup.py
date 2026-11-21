"""Read-only demo fingerprints and exported snapshot for a verified private backup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sys
import time

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

CORE = {'users', 'events', 'lab_sessions', 'rooms', 'seats', 'session_seats',
        'room_layouts', 'reservations', 'staff_assignments', 'checkin_policy_events'}


def canonical_constraint(table,name,definition):
    column={('users','users_role_check'):'role',('users','users_status_check'):'status'}.get((table,name))
    if column is None:return definition
    # pg_dump round trips can move varchar-to-text casts from an array to its
    # elements. Normalize only this single-column, text-enum grammar; every
    # other expression remains byte-sensitive and fails closed on differences.
    literal=r"'((?:[^']|'')*)'"
    values=re.findall(literal,definition)
    remaining=re.sub(literal,'',definition)
    tokens=re.findall(r'[A-Za-z_][A-Za-z_0-9]*',remaining)
    upper=[token.upper() for token in tokens]
    allowed={'CHECK',column.upper(),'ANY','ARRAY','CHARACTER','VARYING','TEXT'}
    punctuation=re.sub(r'[A-Za-z_][A-Za-z_0-9]*','',remaining)
    if (not values or any(token not in allowed for token in upper)
        or any(upper.count(token)!=1 for token in ('CHECK',column.upper(),'ANY','ARRAY'))
        or remaining.count('=')!=1 or re.search(r'[^\s():=\[\],]',punctuation)):
        return definition
    return 'TEXT_ENUM_CHECK:'+column+':'+json.dumps(sorted(set(v.replace("''", "'") for v in values)))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def fingerprint(connection, original=None, business=False):
    tables = connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    result = {'tables': {}, 'core': {}}
    for (table,) in tables:
        if (business or original is not None) and table not in CORE:continue
        primary = connection.execute("""SELECT a.attname FROM pg_index i
            JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
            WHERE i.indrelid=to_regclass(%s) AND i.indisprimary ORDER BY a.attnum""", ('public.'+table,)).fetchall()
        pk = [row[0] for row in primary]
        keys, digest, count = [], hashlib.sha256(), 0
        selection = sql.SQL('jsonb_build_array({})::text').format(sql.SQL(',').join(sql.Identifier('t', key) for key in pk)) if pk else sql.SQL('NULL')
        business_user=table=='users' and (business or bool(original and original.get('business_core')))
        document=sql.SQL("(to_jsonb(t)-'last_activity_at')::text") if business_user else sql.SQL('to_jsonb(t)::text')
        query = sql.SQL('SELECT {}, {} FROM public.{} t').format(document,selection,sql.Identifier(table))
        parameters = ()
        if original is not None:
            if table not in original['core']:continue
            query += sql.SQL(' WHERE {} = ANY(%s)').format(selection)
            parameters = (original['core'][table]['keys'],)
        query += sql.SQL(' ORDER BY {} COLLATE "C"').format(document)
        for body, key in connection.execute(query, parameters):
            digest.update(body.encode('utf-8')+b'\n');count += 1
            if table in CORE:keys.append(key)
        item = {'rows': count, 'sha256': digest.hexdigest()}
        result['tables'][table] = item
        if table in CORE:
            if not pk:raise RuntimeError('Core table requires a primary key')
            result['core'][table] = item | {'keys': keys}
    constraints = connection.execute("""SELECT conrelid::regclass::text, conname,
        pg_get_constraintdef(oid), convalidated FROM pg_constraint
        WHERE connamespace='public'::regnamespace ORDER BY conrelid::regclass::text, conname""").fetchall()
    constraints.sort(key=lambda row: (row[0],row[1]))
    result['constraints'] = constraints
    result['raw_constraints_sha256'] = hashlib.sha256(json.dumps(constraints,ensure_ascii=False).encode()).hexdigest()
    semantic=[(table,name,canonical_constraint(table,name,definition),validated) for table,name,definition,validated in constraints]
    result['constraints_sha256'] = hashlib.sha256(json.dumps(semantic,ensure_ascii=False).encode()).hexdigest()
    result['schema_revision'] = connection.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    result['db_clock'] = connection.execute('SELECT clock_timestamp()').fetchone()[0].isoformat()
    result['server_version'] = connection.execute('SHOW server_version').fetchone()[0]
    invariant_file=Path(__file__).resolve().parents[2]/'tests/db-invariants.sql'
    statements='\n'.join(line for line in invariant_file.read_text().splitlines() if not line.lstrip().startswith('--'))
    checks=[]
    for statement in statements.split(';'):
        query=statement.strip()
        if not query or query.upper().startswith(('BEGIN','COMMIT')):continue
        if not query.upper().startswith('SELECT'):raise ValueError('Invariant SQL must be read-only')
        checks.append(len(connection.execute(query).fetchall()))
    if checks!=[0]*7:raise RuntimeError('Database invariants failed')
    result['invariant_rows']=checks
    return result


def image_references(connection):
    values = set()
    def collect(value):
        if isinstance(value,dict):
            for item in value.values():collect(item)
        elif isinstance(value,list):
            for item in value:collect(item)
        elif isinstance(value,str) and value.startswith(('rooms/','events/','users/')) and value.lower().endswith(('.jpg','.jpeg','.png','.webp')):
            values.add(value)
    for table,column in [('rooms','image_key'),('events','poster_key'),('users','avatar_key'),('room_layouts','layout')]:
        for (value,) in connection.execute(sql.SQL('SELECT {} FROM public.{}').format(sql.Identifier(column),sql.Identifier(table))):collect(value)
    return sorted(values)


def backup_assets(output,config):
    import boto3
    from botocore.config import Config
    credentials=config['credentials']
    session=boto3.Session(aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials.get('SessionToken'),region_name='ap-southeast-2')
    sdk=Config(connect_timeout=5,read_timeout=30,retries={'mode':'standard','max_attempts':2})
    if session.client('sts',config=sdk).get_caller_identity()['Account']!=config['expected_account']:
        raise ValueError('Unexpected AWS account')
    store=session.client('s3',config=sdk);bucket=config['bucket'];run=config['run']
    if run!='demo-load-20261121a':raise ValueError('Explicit backup run required')
    protection=store.get_public_access_block(Bucket=bucket)['PublicAccessBlockConfiguration']
    if not all(protection.values()) or store.get_bucket_policy_status(Bucket=bucket)['PolicyStatus']['IsPublic']:
        raise ValueError('Backup bucket must remain private')
    versioning=store.get_bucket_versioning(Bucket=bucket).get('Status')
    if versioning!='Enabled':raise ValueError('Versioning must be enabled before backup')
    baseline=json.loads((output/'source-fingerprint.json').read_text())
    def read(key,version):
        request={'Bucket':bucket,'Key':key}
        if version:request['VersionId']=version
        response=store.get_object(**request)
        try:return response['Body'].read(),response.get('ContentType')
        finally:response['Body'].close()
    if config.get('verify_only'):
        assets=json.loads((output/'assets-backup.private.json').read_text())['assets']
        for item in assets:
            if store.head_object(Bucket=bucket,Key=item['source_key']).get('VersionId')!=item['source_version']:
                raise RuntimeError('A demo image source version changed')
            for key,version in ((item['source_key'],item['source_version']),(item['backup_key'],item['backup_version'])):
                body,content_type=read(key,version)
                if hashlib.sha256(body).hexdigest()!=item['sha256'] or content_type!=item['content_type']:
                    raise RuntimeError('Demo/backup asset content changed')
        write(output/'assets-source-check.private.json',{'verified':True,'count':len(assets),
            'verified_at_utc':datetime.now(timezone.utc).isoformat()})
        print('DEMO_ASSETS_UNCHANGED='+str(len(assets)),flush=True)
        return
    records=[]
    for relative in baseline['assets']:
        source='/'.join(filter(None,(config['prefix'].strip('/'),relative)))
        head=store.head_object(Bucket=bucket,Key=source)
        version=head.get('VersionId')
        body,content_type=read(source,version)
        digest=hashlib.sha256(body).hexdigest()
        destination=f'assessment/backups/demo/{run}/assets/{hashlib.sha256(relative.encode()).hexdigest()}.bin'
        copy_source={'Bucket':bucket,'Key':source}
        if version:copy_source['VersionId']=version
        copied=store.copy_object(Bucket=bucket,Key=destination,CopySource=copy_source,
            ServerSideEncryption='AES256',TaggingDirective='REPLACE',
            Tagging=f'owner=person2&purpose=protect-final-demo&assessment-run={run}')
        restored,restored_type=read(destination,copied.get('VersionId'))
        if hashlib.sha256(restored).hexdigest()!=digest or restored_type!=content_type:
            raise RuntimeError('Asset backup verification failed')
        records.append({'reference':relative,'source_key':source,'source_version':version,
            'backup_key':destination,'backup_version':copied.get('VersionId'),
            'sha256':digest,'bytes':len(body),'content_type':content_type})
        write(output/'assets-backup-progress.private.json',{'assets':records})
    result={'verified':True,'bucket':bucket,'versioning':versioning,
        'public_access_block':protection,'assets':records,'verified_at_utc':datetime.now(timezone.utc).isoformat()}
    write(output/'assets-backup.private.json',result)
    print('ASSETS_BACKUP_VERIFIED='+json.dumps({'count':len(records),'bytes':sum(r['bytes'] for r in records)}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('export','verify','verify-demo','capture-demo','assets'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-host')
    parser.add_argument('--baseline',type=Path)
    args=parser.parse_args()
    config=json.loads(sys.stdin.readline())
    if args.mode=='assets':
        backup_assets(args.output,config)
        return
    if not args.expected_host:raise ValueError('Expected database host is required')
    url=make_url(config['url'])
    if url.host!=args.expected_host:raise ValueError('Database host mismatch')
    options={'host':url.host,'port':config.get('port',url.port or 5432),
        'user':url.username,'password':url.password,'dbname':url.database,
        'connect_timeout':5,'options':'-c timezone=UTC -c search_path=public -c statement_timeout=30000 -c lock_timeout=5000'}
    if args.expected_host.endswith('.rds.amazonaws.com'):
        options.update(sslmode='verify-full',sslrootcert='/srv/labseat/app/infrastructure/database/rds-global-bundle.crt',hostaddr=config['hostaddr'])
    elif args.expected_host!='backup-verify-db' or not url.database.endswith('_test'):
        raise ValueError('Local verification is restricted to the disposable test database')
    baseline=json.loads(args.baseline.read_text()) if args.baseline else None
    with psycopg.connect(autocommit=True,**options) as connection:
        connection.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        if args.mode=='capture-demo':
            if args.expected_host!='backup-verify-db' or baseline is None:raise ValueError('Capture business baseline only from the verified restored DB')
            restored=fingerprint(connection)
            if restored['tables']!=baseline['tables'] or restored['constraints_sha256']!=baseline['constraints_sha256']:
                raise RuntimeError('Restored backup must match before capturing its business baseline')
            result=fingerprint(connection,business=True)
            result['business_core']=True
            result['ignored_operational_fields']={'users':['last_activity_at']}
            write(args.output/'demo-fingerprint.json',result)
            print('DEMO_BUSINESS_BASELINE_CAPTURED',flush=True)
            return
        result=fingerprint(connection,baseline if args.mode=='verify-demo' else None)
        if args.mode=='export':
            result['assets']=image_references(connection)
            result['snapshot_id']=connection.execute('SELECT pg_export_snapshot()').fetchone()[0]
            write(args.output/'source-fingerprint.json',result)
            write(args.output/'snapshot-ready.json',{'snapshot_id':result['snapshot_id'],'db_clock':result['db_clock']})
            print('BACKUP_SNAPSHOT_READY',flush=True)
            start=time.monotonic()
            while not (args.output/'dump-complete.flag').exists():
                if time.monotonic()-start>900:raise TimeoutError('Snapshot holder expired; backup was not confirmed')
                time.sleep(1)
        else:
            if baseline is None:raise ValueError('Verification requires the source fingerprint')
            expected={key:baseline['tables'][key] for key in result['tables']} if args.mode=='verify-demo' else baseline['tables']
            result['verified']=result['tables']==expected and result['schema_revision']==baseline['schema_revision']
            if args.mode=='verify':result['verified']=result['verified'] and result['constraints_sha256']==baseline['constraints_sha256']
            write(args.output/(args.mode+'-result.json'),result)
            if not result['verified']:raise RuntimeError('Backup/demo comparison failed; do not prepare load data')
            print('BACKUP_VERIFIED='+json.dumps({'tables':len(result['tables']),'schema':result['schema_revision'],'verified':True}),flush=True)


if __name__=='__main__':main()
