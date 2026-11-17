#!/usr/bin/env python3
"""Explicitly invoked local deployment driver. Never applies Terraform."""
import json
from contextlib import contextmanager
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.getenv('DEPLOY_STATE_DIR', ROOT / '.local'))
STATE = STATE_DIR / 'ecs-last-good.json'
TIMEOUT = int(os.getenv('DEPLOY_TIMEOUT_SECONDS', '900'))
TASK_TIMEOUT = int(os.getenv('TASK_TIMEOUT_SECONDS', '300'))


def run(argv, *, capture=True, input=None, timeout=60):
    result = subprocess.run(argv, input=input, text=True, capture_output=capture, timeout=timeout)
    if result.returncode:
        # External errors can contain sensitive runtime values. Do not echo them.
        raise RuntimeError(f'{argv[0]} command failed (exit {result.returncode}); inspect configuration securely')
    return result.stdout if capture else ''


def release():
    value = os.environ['RELEASE_ID']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', value) or value == 'latest':
        raise ValueError('RELEASE_ID must be a unique immutable release identifier')
    return value


def aws(*args):
    value = run(['aws', '--profile', os.environ['AWS_PROFILE'], '--region', os.environ['AWS_REGION'],
                 '--no-cli-pager', *args, '--output', 'json'], timeout=45)
    return json.loads(value) if value.strip() else {}


def config():
    for key in ('AWS_PROFILE', 'AWS_REGION', 'EXPECTED_AWS_ACCOUNT_ID'):
        if not os.getenv(key):
            raise ValueError(f'Explicit {key} is required')
    cfg = json.loads(Path(os.getenv('DEPLOY_CONFIG', STATE_DIR / 'ecs-deployment.json')).read_text())
    if cfg['account'] != os.environ['EXPECTED_AWS_ACCOUNT_ID'] or cfg['region'] != os.environ['AWS_REGION']:
        raise ValueError('Deployment configuration account/region mismatch')
    if aws('sts', 'get-caller-identity')['Account'] != cfg['account']:
        raise ValueError('Authenticated AWS account mismatch')
    return cfg


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def diagnostics(cfg):
    response = aws('ecs', 'describe-services', '--cluster', cfg['cluster'], '--services', *cfg['services'].values())
    for service in response.get('services', []):
        print(json.dumps({k: service.get(k) for k in ('serviceName', 'desiredCount', 'runningCount', 'pendingCount')}))
        for event in service.get('events', [])[:5]:
            print(event.get('message', ''))


def wait_task(cfg, task, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = aws('ecs', 'describe-tasks', '--cluster', cfg['cluster'], '--tasks', task)
        if response.get('failures') or not response.get('tasks'):
            raise RuntimeError('Cannot inspect one-off task')
        record = response['tasks'][0]
        if record['lastStatus'] == 'STOPPED':
            containers = record.get('containers', [])
            if not containers or any(c.get('exitCode') != 0 for c in containers):
                print('One-off task failed; inspect its CloudWatch stream and ECS stopCode:', record.get('stopCode'))
                raise RuntimeError('One-off task did not exit successfully')
            return
        time.sleep(5)
    aws('ecs', 'stop-task', '--cluster', cfg['cluster'], '--task', task,
        '--reason', 'Local deployment one-off task timeout')
    diagnostics(cfg)
    raise TimeoutError('One-off task timed out; check ENI/CPU/memory/Capacity Provider and task logs')


def one_off(cfg, definition, command, timeout):
    network = {'awsvpcConfiguration': {'subnets': cfg['subnets'], 'securityGroups': cfg['security_groups'], 'assignPublicIp': 'DISABLED'}}
    result = aws('ecs', 'run-task', '--cluster', cfg['cluster'], '--task-definition', definition,
        '--capacity-provider-strategy', json.dumps([{'capacityProvider': cfg['capacity_provider'], 'weight': 1}]),
        '--network-configuration', json.dumps(network), '--count', '1', '--client-token', str(uuid.uuid4()),
        '--overrides', json.dumps({'containerOverrides': [{'name': 'app', 'command': command}]}))
    if result.get('failures') or len(result.get('tasks', [])) != 1:
        diagnostics(cfg)
        raise RuntimeError('One-off task placement failed; no automatic mutation retry')
    task = result['tasks'][0]['taskArn']
    try:
        wait_task(cfg, task, timeout)
    except KeyboardInterrupt:
        aws('ecs', 'stop-task', '--cluster', cfg['cluster'], '--task', task,
            '--reason', 'Local one-off task interrupted by operator')
        raise


def definition(cfg, role, image):
    template = aws('ecs', 'describe-task-definition', '--task-definition', (cfg['maintenance']['task_definition'] if role=='maintenance' else cfg['task_definitions'][role]))['taskDefinition']
    allowed = ('family', 'taskRoleArn', 'executionRoleArn', 'networkMode', 'containerDefinitions', 'volumes',
               'placementConstraints', 'requiresCompatibilities', 'cpu', 'memory', 'runtimePlatform', 'ephemeralStorage')
    body = {key: template[key] for key in allowed if key in template}
    for container in body['containerDefinitions']:
        container['image'] = image
        container['environment'] = [v for v in container.get('environment', []) if v['name'] != 'RELEASE_ID'] + [{'name': 'RELEASE_ID', 'value': release()}]
    # CLI JSON via stdin avoids shell interpretation and temporary runtime definition files.
    return aws('ecs', 'register-task-definition', '--cli-input-json', json.dumps(body))['taskDefinition']['taskDefinitionArn']


def maintenance_schedule(cfg,definition=None,enabled=False):
    if not cfg.get('maintenance'):return
    record=aws('scheduler','get-schedule','--name',cfg['maintenance']['schedule'])
    allowed=('Name','GroupName','ScheduleExpression','StartDate','EndDate','Description',
        'ScheduleExpressionTimezone','KmsKeyArn','Target','FlexibleTimeWindow','ActionAfterCompletion')
    body={k:record[k] for k in allowed if k in record}
    body['State']='ENABLED' if enabled else 'DISABLED'
    if definition:body['Target']['EcsParameters']['TaskDefinitionArn']=definition
    aws('scheduler','update-schedule','--cli-input-json',json.dumps(body))


def wait_services(cfg, definitions, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = aws('ecs', 'describe-services', '--cluster', cfg['cluster'], '--services', *cfg['services'].values())
        if result.get('failures') or len(result.get('services', [])) != len(definitions):
            raise RuntimeError('Missing ECS services')
        done = True
        for role, name in cfg['services'].items():
            service = next(s for s in result['services'] if s['serviceName'] == name)
            primary = next((d for d in service['deployments'] if d['status'] == 'PRIMARY'), {})
            if primary.get('taskDefinition') != definitions[role] or primary.get('rolloutState') == 'FAILED':
                diagnostics(cfg)
                raise RuntimeError('Deployment failed or rolled back to another revision')
            done &= (len(service['deployments']) == 1 and primary.get('rolloutState') == 'COMPLETED'
                and service['runningCount'] == service['desiredCount'] and service['pendingCount'] == 0)
        if done:
            return
        time.sleep(5)
    diagnostics(cfg)
    raise TimeoutError('ECS rollout timeout; do not blindly retry. Use rollback.sh after reviewing capacity/events')


def smoke(cfg, definitions, image):
    # Require exact API release definition/image, never an old ALB target.
    td = aws('ecs', 'describe-task-definition', '--task-definition', definitions['api'])['taskDefinition']
    if td['containerDefinitions'][0]['image'] != image or '@sha256:' not in image:
        raise RuntimeError('Release image mismatch or mutable image')
    task_arns = aws('ecs', 'list-tasks', '--cluster', cfg['cluster'], '--service-name', cfg['services']['api'], '--desired-status', 'RUNNING')['taskArns']
    if not task_arns:
        raise RuntimeError('No running API release tasks')
    for offset in range(0, len(task_arns), 100):
        tasks = aws('ecs', 'describe-tasks', '--cluster', cfg['cluster'], '--tasks', *task_arns[offset:offset+100])
        if tasks.get('failures') or any(t['taskDefinitionArn'] != definitions['api'] for t in tasks['tasks']):
            raise RuntimeError('API still contains another release')
    one_off(cfg, definitions['api'], ['python', '-m', 'app.smoke'], TASK_TIMEOUT)
    print('Exact release image and PostgreSQL smoke passed')


def push(cfg):
    tag = release()
    repository = cfg['repository']
    password = run(['aws', '--profile', os.environ['AWS_PROFILE'], '--region', os.environ['AWS_REGION'], 'ecr', 'get-login-password'])
    run(['docker', 'login', '--username', 'AWS', '--password-stdin', repository.split('/')[0]], input=password)
    run(['docker', 'tag', f'labseat-app:{tag}', f'{repository}:{tag}'])
    run(['docker', 'push', f'{repository}:{tag}'], capture=False, timeout=900)
    digest = aws('ecr', 'describe-images', '--repository-name', repository.split('/', 1)[1], '--image-ids', f'imageTag={tag}')['imageDetails'][0]['imageDigest']
    image = f'{repository}@{digest}'
    atomic_json(STATE_DIR / f'ecs-image-{tag}.json', {'image': image})
    return image


@contextmanager
def deployment_lock():
    import fcntl
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / 'ecs-operation.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another deployment command is using this state directory') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def main():
    os.environ['AWS_MAX_ATTEMPTS'] = '1'  # no hidden retries of unknown-result mutations
    os.environ['AWS_PAGER'] = ''
    action = sys.argv[1]
    if action == 'build':
        run(['docker', 'build', '--platform', 'linux/amd64', '-f', 'app/Dockerfile', '-t', f'labseat-app:{release()}', '.'], capture=False, timeout=1200)
        return
    with deployment_lock():
        cfg = config()
        if STATE.exists():
            recorded = json.loads(STATE.read_text())
            if recorded['account'] != cfg['account'] or recorded['cluster'] != cfg['cluster']:
                raise ValueError('Use a separate DEPLOY_STATE_DIR for each environment')
        if action == 'push':
            print(push(cfg))
            return
        if action == 'verify':
            diagnostics(cfg)
            good = json.loads(STATE.read_text())
            wait_services(cfg, good['definitions'], TIMEOUT)
            smoke(cfg, good['definitions'], good['image'])
            return
        if action == 'rollback':
            good = json.loads(STATE.read_text())
            candidate_path = STATE_DIR / 'ecs-candidate.json'
            if candidate_path.exists() and json.loads(candidate_path.read_text())['definitions'] == good['definitions']:
                previous = STATE_DIR / 'ecs-previous-good.json'
                if not previous.exists():
                    raise RuntimeError('No earlier successful release exists to roll back to')
                good = json.loads(previous.read_text())
            if good['account'] != cfg['account'] or good['cluster'] != cfg['cluster']:
                raise ValueError('Last-good release belongs to another environment')
            for role, arn in good['definitions'].items():
                aws('ecs', 'update-service', '--cluster', cfg['cluster'], '--service', cfg['services'][role], '--task-definition', arn)
            wait_services(cfg, good['definitions'], TIMEOUT)
            smoke(cfg, good['definitions'], good['image'])
            maintenance_schedule(cfg,good.get('maintenance'),enabled=bool(good.get('maintenance')))
            atomic_json(STATE, good)
            print('Restored last known-good release; database migrations retained')
            return
        image = json.loads((STATE_DIR / f'ecs-image-{release()}.json').read_text())['image']
        if not image.startswith(cfg['repository'] + '@sha256:'):
            raise ValueError('Image does not belong to the configured repository')
        if action == 'deploy':
            maintenance=definition(cfg,'maintenance',image) if cfg.get('maintenance') else None
            maintenance_schedule(cfg,enabled=False)
            definitions = {role: definition(cfg, role, image) for role in cfg['services']}
            atomic_json(STATE_DIR / 'ecs-candidate.json', {'definitions': definitions, 'image': image})
            one_off(cfg, definitions['api'], ['python', '-m', 'app.migrate'], TASK_TIMEOUT)
            existing = aws('ecs', 'describe-services', '--cluster', cfg['cluster'], '--services', *cfg['services'].values())['services']
            for role, arn in definitions.items():
                service = next(s for s in existing if s['serviceName'] == cfg['services'][role])
                extra = ['--desired-count', str(cfg['api_tasks']['min'] if role == 'api' else 1)] if service['desiredCount'] == 0 else []
                aws('ecs', 'update-service', '--cluster', cfg['cluster'], '--service', cfg['services'][role], '--task-definition', arn, *extra)
            aws('application-autoscaling', 'register-scalable-target', '--service-namespace', 'ecs',
                '--resource-id', f"service/{cfg['cluster']}/{cfg['services']['api']}",
                '--scalable-dimension', 'ecs:service:DesiredCount', '--min-capacity', str(cfg['api_tasks']['min']),
                '--max-capacity', str(cfg['api_tasks']['max']))
            wait_services(cfg, definitions, TIMEOUT)
            smoke(cfg, definitions, image)
            if maintenance:
                one_off(cfg,maintenance,['python','-m','app.maintenance','--limit','1'],TASK_TIMEOUT)
                maintenance_schedule(cfg,maintenance,enabled=True)
            if STATE.exists():
                previous = json.loads(STATE.read_text())
                if previous['account'] != cfg['account'] or previous['cluster'] != cfg['cluster']:
                    raise ValueError('Use a separate DEPLOY_STATE_DIR for each environment')
                atomic_json(STATE_DIR / 'ecs-previous-good.json', previous)
            atomic_json(STATE, {'account': cfg['account'], 'cluster': cfg['cluster'], 'definitions': definitions, 'image': image, 'release': release(),'maintenance':maintenance})
            print('Release is healthy; last-good deployment recorded')
        elif action == 'migrate':
            definitions = {role: definition(cfg, role, image) for role in cfg['services']}
            atomic_json(STATE_DIR / 'ecs-candidate.json', {'definitions': definitions, 'image': image})
            one_off(cfg, definitions['api'], ['python', '-m', 'app.migrate'], TASK_TIMEOUT)
        elif action == 'smoke-test':
            candidate = json.loads((STATE_DIR / 'ecs-candidate.json').read_text())
            if candidate['image'] != image:
                raise ValueError('Candidate and requested release mismatch')
            smoke(cfg, candidate['definitions'], image)
        else:
            raise ValueError('Unknown action')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(f'Deployment stopped: {type(exc).__name__}. {exc if isinstance(exc, (ValueError, RuntimeError, TimeoutError)) else "Inspect configuration securely."}', file=sys.stderr)
        print('Review ECS events and capacity. If a previous successful release exists, run deploy/rollback.sh. First release has no last-good rollback.', file=sys.stderr)
        sys.exit(1)
