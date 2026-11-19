"""Build a private RDS PITR request and cleanup identity; performs no AWS writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def build(source, config):
    source = source['DBInstances'][0] if 'DBInstances' in source else source
    run_id = str(uuid.UUID(config['run_id']))
    target = config['target_db']
    if not re.fullmatch(r'labseat-b4-[a-z0-9]+(?:-[a-z0-9]+)*', target) or len(target) > 63:
        raise ValueError('Dedicated labseat-b4-* DB identifier required')
    if target == source['DBInstanceIdentifier']:
        raise ValueError('Target must differ from source')
    if source['Engine'] != 'postgres' or source.get('DBClusterIdentifier'):
        raise ValueError('B4 plan only supports the PostgreSQL DB instance API')
    if source['PubliclyAccessible'] or not source['StorageEncrypted']:
        raise ValueError('Expected private encrypted source')
    incident, restore = stamp(config['incident_at']), stamp(config['restore_time'])
    earliest, latest = stamp(config['earliest_restorable_time']), stamp(source['LatestRestorableTime'])
    if not earliest <= restore <= latest or restore > incident:
        raise ValueError('Target outside actual restore window or after incident')
    if not config['security_groups'] or any(not value.startswith('sg-') for value in config['security_groups']):
        raise ValueError('Explicit restored DB security groups required')
    if set(config['security_groups']) & {x['VpcSecurityGroupId'] for x in source['VpcSecurityGroups']}:
        raise ValueError('Use dedicated recovery DB security groups')
    request = {
        'SourceDBInstanceIdentifier': source['DBInstanceIdentifier'],
        'TargetDBInstanceIdentifier': target, 'RestoreTime': restore.astimezone(timezone.utc).isoformat(),
        'DBInstanceClass': source['DBInstanceClass'], 'StorageType': source['StorageType'],
        'DBSubnetGroupName': source['DBSubnetGroup']['DBSubnetGroupName'],
        'DBParameterGroupName': source['DBParameterGroups'][0]['DBParameterGroupName'],
        'VpcSecurityGroupIds': config['security_groups'], 'PubliclyAccessible': False,
        'MultiAZ': config['multi_az'], 'Port': source['Endpoint']['Port'], 'DeletionProtection': False,
        'Tags': [{'Key': 'assessment', 'Value': 'B4'}, {'Key': 'run', 'Value': run_id},
                 {'Key': 'owner', 'Value': config['owner']}],
    }
    if not isinstance(config['multi_az'], bool) or not config['owner']:
        raise ValueError('Explicit boolean MultiAZ choice and owner required')
    return {'status': 'PLAN_ONLY', 'restore_input': request,
            'cleanup_identity': {'source_db_never_delete': source['DBInstanceIdentifier'],
                                 'target_db': target, 'required_tags': {'assessment': 'B4', 'run': run_id},
                                 'owner': config['owner']},
            'required_before_execute': ['C4/C5 stable handoff and exclusive rehearsal window',
                'Committed source markers and private baseline evidence; recheck restore window at execution',
                'Verified dedicated SG, role/secret/cache/storage setup and capacity',
                'Use inherited source encryption; verify actual restored DB is encrypted and private',
                'On cleanup re-describe exact target and verify tags/source inequality before deletion; keep evidence first'],
            'note': 'Private API request only. No restore or cleanup is submitted, no RPO/RTO measured.'}


def cleanup_plan(state, plan):
    state = state['DBInstances'][0] if 'DBInstances' in state else state
    identity = plan['cleanup_identity']
    target = state['DBInstanceIdentifier']
    if target != identity['target_db'] or target == identity['source_db_never_delete'] or not target.startswith('labseat-b4-'):
        raise ValueError('Cleanup target differs from manifest or is the source')
    tags = {item['Key']: item['Value'] for item in state.get('TagList', [])}
    if any(tags.get(k) != v for k, v in identity['required_tags'].items()) or tags.get('owner') != identity['owner']:
        raise ValueError('Cleanup ownership/run tags not verified')
    if state.get('DeletionProtection'):
        raise ValueError('Deletion protection enabled; do not automatically disable it')
    return {'status': 'PLAN_ONLY', 'delete_db_input': {'DBInstanceIdentifier': target,
            'SkipFinalSnapshot': True, 'DeleteAutomatedBackups': True},
            'required_before_execute': ['Verify AWS account/region and fresh target tags again',
                'Persist evidence, stop only restored app tasks and verify no connection to this DB remains',
                'Remove only recovery secrets/cache/S3 objects in the same run manifest',
                'After deletion verify target absent; source available and production config unchanged'],
            'note': 'No delete request submitted. No final snapshot retained by this plan.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--source-db', type=Path)
    mode.add_argument('--cleanup-db-state', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--existing-plan', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.source_db:
        result = build(json.loads(args.source_db.read_text(encoding='utf-8-sig')),
                       json.loads(args.config.read_text(encoding='utf-8-sig')))
    else:
        result = cleanup_plan(json.loads(args.cleanup_db_state.read_text(encoding='utf-8-sig')),
                              json.loads(args.existing_plan.read_text(encoding='utf-8-sig')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Private PITR plan saved; no AWS request submitted')


if __name__ == '__main__':
    main()
