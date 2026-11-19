"""Build private ECS registration/run input for an isolated B4 API; never submits it."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import uuid


def build(source, config):
    task = source.get('taskDefinition', source)
    container = next(c for c in task['containerDefinitions'] if c['name'] == 'app')
    image = container['image']
    if not re.fullmatch(r'.+@sha256:[a-f0-9]{64}', image):
        raise ValueError('Source API must reference an immutable image digest')
    family = config['family']
    run_id = str(uuid.UUID(config['run_id']))
    if not re.fullmatch(r'labseat-b4-[a-z0-9-]{6,48}', family):
        raise ValueError('Use a dedicated labseat-b4-* task family')
    for role in ['taskRoleArn', 'executionRoleArn']:
        if not config[role] or config[role] == task.get(role):
            raise ValueError('Use dedicated recovery task/execution roles')
    original_secrets = {s['valueFrom'] for c in task['containerDefinitions'] for s in c.get('secrets', [])}
    required = {'DATABASE_URL', 'REDIS_URL', 'REDIS_USERNAME', 'REDIS_PASSWORD', 'REDIS_CA_CERT'}
    secrets = config['secrets']
    if set(secrets) != required or any(not v or v in original_secrets for v in secrets.values()):
        raise ValueError('Require distinct recovery-only database/Redis secret references')
    if len(set(secrets.values())) != len(secrets):
        raise ValueError('Each recovery setting requires a distinct secret reference')
    if not all(v.startswith('arn:aws:ssm:') and ':parameter/' in v for v in secrets.values()):
        raise ValueError('Expected SSM parameter ARNs, not plaintext values')
    # All source environment, commands, mounts, log config and extra containers are dropped.
    api = {
        'name': 'app', 'image': image, 'essential': True,
        'cpu': container.get('cpu', 0),
        'entryPoint': ['python'],
        'command': ['-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
        'portMappings': [{'containerPort': 8000, 'hostPort': 8000, 'protocol': 'tcp'}],
        'environment': [{'name': k, 'value': v} for k, v in {
            'APP_ENV': 'production', 'AWS_REGION': config['region'],
            'EMAIL_BACKEND': 'disabled', 'STORAGE_BACKEND': 's3',
            'S3_BUCKET': config['bucket'], 'S3_PREFIX': config['prefix'],
            'DB_POOL_SIZE': '3', 'DB_MAX_OVERFLOW': '0', 'COOKIE_SECURE': 'false',
            'EMAIL_PUBLIC_BASE_URL': 'http://127.0.0.1:8000',
        }.items()],
        'secrets': [{'name': k, 'valueFrom': v} for k, v in sorted(secrets.items())],
    }
    for key in ['memory', 'memoryReservation']:
        if key in container:
            api[key] = container[key]
    prefix = config['prefix']
    if not prefix.startswith('assessment/b4/') or not prefix.endswith('/') or '..' in prefix:
        raise ValueError('Use a separate assessment/b4/<run>/ storage prefix')
    if config['bucket'] == '' or not config['subnets'] or not config['security_groups']:
        raise ValueError('Missing storage/private network plan')
    result = {'family': family, 'taskRoleArn': config['taskRoleArn'],
              'executionRoleArn': config['executionRoleArn'], 'networkMode': 'awsvpc',
              'requiresCompatibilities': ['EC2'], 'containerDefinitions': [api],
              'tags': [{'key': 'assessment', 'value': 'B4'}, {'key': 'run', 'value': run_id}]}
    for key in ['cpu', 'memory', 'runtimePlatform']:
        if key in task:
            result[key] = deepcopy(task[key])
    run = {'cluster': config['cluster'], 'taskDefinition': family, 'count': 1, 'launchType': 'EC2',
           'networkConfiguration': {'awsvpcConfiguration': {'subnets': config['subnets'],
              'securityGroups': config['security_groups'], 'assignPublicIp': 'DISABLED'}},
           'tags': result['tags'], 'startedBy': family[:36]}
    return {'register_task_input': result, 'run_task_input': run, 'status': 'PLAN_ONLY',
            'required_external_checks': [
                'Resolve the family to the exact newly registered task-definition ARN before run-task',
                'Verify secrets resolve to restored DB and isolated Redis, never production endpoints',
                'Verify dedicated IAM roles deny production SQS/Brevo and restrict S3 to the test prefix',
                'Verify subnets/routes/SG egress isolate production DB/Redis/SQS; no ALB/service attachment',
                'Private HTTP probe only: COOKIE_SECURE=false is limited to this isolated test task',
                'Provision logging/probe transport without recording credentials or ticket QR payloads',
                'Capacity/placement and C4/C5 stable handoff required before submitting'],
            'note': 'File is private and contains secret/resource ARNs. Not proof of network or IAM isolation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-task', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = build(json.loads(args.source_task.read_text(encoding='utf-8-sig')),
                  json.loads(args.config.read_text(encoding='utf-8-sig')))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print('Private ECS plan written; no AWS request submitted')


if __name__ == '__main__':
    main()
