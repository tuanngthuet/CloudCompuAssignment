"""Collect a sanitized, read-only B4 preflight. Never creates/restores resources."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aws', default='aws')
    parser.add_argument('--profile', required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--expected-account', required=True)
    parser.add_argument('--source-db', required=True)
    parser.add_argument('--cluster', required=True)
    parser.add_argument('--services', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    def aws(*parts):
        command = [args.aws, *parts, '--profile', args.profile, '--region',
                   args.region, '--output', 'json', '--no-cli-pager']
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        if result.returncode:
            # Do not publish raw CLI errors: these can include resource identifiers.
            raise RuntimeError(f'{parts[0]} {parts[1]} failed; inspect privately')
        return json.loads(result.stdout)

    identity = aws('sts', 'get-caller-identity')
    if identity['Account'] != args.expected_account:
        raise RuntimeError('AWS account mismatch; no further requests made')
    db = aws('rds', 'describe-db-instances', '--db-instance-identifier',
             args.source_db)['DBInstances'][0]
    quotas = aws('rds', 'describe-account-attributes')['AccountQuotas']
    quota = next(item for item in quotas if item['AccountQuotaName'] == 'DBInstances')
    backups = aws('rds', 'describe-db-instance-automated-backups',
                  '--db-instance-identifier', args.source_db)['DBInstanceAutomatedBackups']
    orderable = aws('rds', 'describe-orderable-db-instance-options', '--engine',
                    db['Engine'], '--engine-version', db['EngineVersion'],
                    '--db-instance-class', db['DBInstanceClass'])['OrderableDBInstanceOptions']
    kms = aws('kms', 'describe-key', '--key-id', db['KmsKeyId'])['KeyMetadata'] if db.get('KmsKeyId') else {}
    services = aws('ecs', 'describe-services', '--cluster', args.cluster,
                   '--services', *args.services)
    if services.get('failures'):
        raise RuntimeError('ECS service lookup incomplete')
    service_checks = []
    for service in services['services']:
        task = aws('ecs', 'describe-task-definition', '--task-definition',
                   service['taskDefinition'])['taskDefinition']
        containers = []
        for container in task['containerDefinitions']:
            environment = {x['name']: x['value'] for x in container.get('environment', [])}
            containers.append({
                'name': container['name'],
                'image': container['image'],
                'email_backend': environment.get('EMAIL_BACKEND'),
                'email_backend_from_secret': any(x['name'] == 'EMAIL_BACKEND' for x in container.get('secrets', [])),
            })
        task_ids = aws('ecs', 'list-tasks', '--cluster', args.cluster,
                       '--service-name', service['serviceName'])['taskArns']
        running_digests = []
        if task_ids:
            running = aws('ecs', 'describe-tasks', '--cluster', args.cluster, '--tasks', *task_ids)
            if running.get('failures'):
                raise RuntimeError('Running task lookup incomplete')
            running_digests = sorted({c['imageDigest'] for t in running['tasks']
                                      for c in t.get('containers', []) if c.get('imageDigest')})
        service_checks.append({
            'name': service['serviceName'], 'task_revision': task['revision'],
            'desired': service['desiredCount'], 'running': service['runningCount'],
            'pending': service['pendingCount'],
            'deployments_completed': all(x.get('rolloutState') == 'COMPLETED' for x in service['deployments']),
            'containers': containers, 'running_image_digests': running_digests,
        })
    # Avoid publishing account IDs in ECR image URIs; digest remains reproducible.
    for service in service_checks:
        for container in service['containers']:
            container['image'] = container['image'].replace(args.expected_account, '<account>')
    capacity = []
    instances = aws('ecs', 'list-container-instances', '--cluster', args.cluster)['containerInstanceArns']
    if instances:
        inventory = aws('ecs', 'describe-container-instances', '--cluster', args.cluster,
                        '--container-instances', *instances)
        if inventory.get('failures'):
            raise RuntimeError('Container-instance lookup incomplete')
        for instance in inventory['containerInstances']:
            capacity.append({
                'identity_sha256': hashlib.sha256(instance['containerInstanceArn'].encode()).hexdigest(),
                'status': instance['status'], 'agent_connected': instance['agentConnected'],
                'running_tasks': instance['runningTasksCount'], 'pending_tasks': instance['pendingTasksCount'],
                'remaining_resources': instance['remainingResources'],
                'registered_resources': instance['registeredResources'],
            })
    principal = identity['Arn']
    if ':assumed-role/' in principal:
        role_name = principal.split(':assumed-role/', 1)[1].split('/')[0]
        principal = aws('iam', 'get-role', '--role-name', role_name)['Role']['Arn']
    simulation = aws('iam', 'simulate-principal-policy', '--policy-source-arn', principal,
                     '--action-names', 'rds:RestoreDBInstanceToPointInTime', 'rds:DeleteDBInstance',
                     'ecs:RunTask', 'ecs:RegisterTaskDefinition', 'ecs:StopTask',
                     'ssm:PutParameter', 'ssm:DeleteParameter', 'iam:PassRole',
                     'kms:Decrypt', 'kms:CreateGrant')
    result = {
        'task_id': 'B4', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'region': args.region, 'account_verified': True,
        'source_identity_sha256': hashlib.sha256(db['DBInstanceArn'].encode()).hexdigest(),
        'source': {key: db.get(key) for key in [
            'DBInstanceStatus', 'Engine', 'EngineVersion', 'DBInstanceClass', 'MultiAZ',
            'PubliclyAccessible', 'StorageEncrypted', 'BackupRetentionPeriod',
            'EarliestRestorableTime', 'LatestRestorableTime', 'AllocatedStorage', 'StorageType']},
        'network': {
            'subnet_group_status': db['DBSubnetGroup']['SubnetGroupStatus'],
            'subnet_az_count': len({x['SubnetAvailabilityZone']['Name'] for x in db['DBSubnetGroup']['Subnets']}),
            'security_group_statuses': [x['Status'] for x in db['VpcSecurityGroups']],
            'parameter_group_statuses': [x['ParameterApplyStatus'] for x in db['DBParameterGroups']],
        },
        'db_instance_quota': quota,
        'automated_backup_restore_windows': [x.get('RestoreWindow', {}) for x in backups],
        'container_capacity': capacity,
        'iam_simulation': [{'action': x['EvalActionName'], 'decision': x['EvalDecision'],
                            'missing_context': x.get('MissingContextValues', [])}
                           for x in simulation['EvaluationResults']],
        'orderable_options': [{key: x.get(key) for key in [
            'DBInstanceClass', 'EngineVersion', 'StorageType', 'Vpc', 'MultiAZCapable',
            'MinStorageSize', 'MaxStorageSize']} for x in orderable],
        'kms': {key: kms.get(key) for key in ['KeyState', 'Enabled', 'KeyManager', 'KeyUsage']},
        'services': service_checks,
        'status': 'BLOCKED',
        'reason': 'C4/C5 stability handoff, marker series and isolated restored-app verification are not evidenced by this collector.',
        'not_proven': ['Actual IAM/KMS restore authorization', 'Successful placement of isolated app with required ENI/RAM',
                       'Isolated app/Redis/storage/secret/egress setup', 'SQL correctness in a restored database',
                       'B5 image restore', 'RPO/RTO'],
        'mutations_performed': [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Read-only B4 preflight saved; restore remains BLOCKED')


if __name__ == '__main__':
    main()
