"""Local orchestration failure tests; these make no AWS calls."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('ecs_deploy', Path(__file__).resolve().parents[2] / 'deploy/ecs.py')
ecs = importlib.util.module_from_spec(spec); spec.loader.exec_module(ecs)
CFG = {'cluster': 'test', 'services': {'api': 'api'}, 'capacity_provider': 'cp', 'subnets': ['private-a', 'private-b'], 'security_groups': ['private']}


def test_migration_timeout_stops_task_and_diagnoses(monkeypatch):
    calls = []
    def aws(*args):
        calls.append(args)
        if args[:2] == ('ecs', 'describe-tasks'):
            return {'tasks': [{'lastStatus': 'PROVISIONING'}]}
        return {'services': []}
    clock = iter([0, 0, 20])
    monkeypatch.setattr(ecs, 'aws', aws)
    monkeypatch.setattr(ecs.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(ecs.time, 'sleep', lambda _: None)
    with pytest.raises(TimeoutError): ecs.wait_task(CFG, 'task', 10)
    assert any(call[:2] == ('ecs', 'stop-task') for call in calls)
    assert any(call[:2] == ('ecs', 'describe-services') for call in calls)


def test_failed_migration_exit_blocks_release(monkeypatch):
    monkeypatch.setattr(ecs, 'aws', lambda *a: {'tasks': [{'lastStatus': 'STOPPED', 'containers': [{'exitCode': 1}]}]})
    with pytest.raises(RuntimeError): ecs.wait_task(CFG, 'task', 10)


def test_placement_failure_is_not_retried(monkeypatch):
    calls = []
    def aws(*args):
        calls.append(args)
        return {'failures': [{'reason': 'RESOURCE:ENI'}]} if args[1] == 'run-task' else {'services': []}
    monkeypatch.setattr(ecs, 'aws', aws)
    with pytest.raises(RuntimeError): ecs.one_off(CFG, 'revision', ['python', '-m', 'app.migrate'], 10)
    assert sum(a[1] == 'run-task' for a in calls) == 1


def test_rollback_revision_is_not_accepted_as_candidate(monkeypatch):
    monkeypatch.setattr(ecs, 'diagnostics', lambda _: None)
    monkeypatch.setattr(ecs, 'aws', lambda *a: {'services': [{'serviceName': 'api', 'deployments': [{'status': 'PRIMARY', 'taskDefinition': 'old', 'rolloutState': 'COMPLETED'}]}]})
    with pytest.raises(RuntimeError): ecs.wait_services(CFG, {'api': 'new'}, 10)


def test_release_smoke_rejects_wrong_image(monkeypatch):
    monkeypatch.setattr(ecs, 'aws', lambda *a: {'taskDefinition': {'containerDefinitions': [{'image': 'old@sha256:123'}]}})
    with pytest.raises(RuntimeError): ecs.smoke(CFG, {'api': 'new'}, 'new@sha256:456')


def test_release_smoke_rejects_old_api_task(monkeypatch):
    def aws(*a):
        if a[1] == 'describe-task-definition':
            return {'taskDefinition': {'containerDefinitions': [{'image': 'new@sha256:123'}]}}
        if a[1] == 'list-tasks': return {'taskArns': ['old-task']}
        return {'tasks': [{'taskDefinitionArn': 'old'}]}
    monkeypatch.setattr(ecs, 'aws', aws)
    with pytest.raises(RuntimeError): ecs.smoke(CFG, {'api': 'new'}, 'new@sha256:123')


def test_rollback_after_success_uses_previous_good(tmp_path, monkeypatch):
    import json
    cfg = CFG | {'account': '123456789012'}
    current = {'account': cfg['account'], 'cluster': cfg['cluster'], 'definitions': {'api': 'new'}, 'image': 'new@sha256:123'}
    previous = current | {'definitions': {'api': 'previous'}, 'image': 'previous@sha256:456'}
    state = tmp_path / 'ecs-last-good.json'
    state.write_text(json.dumps(current))
    (tmp_path / 'ecs-previous-good.json').write_text(json.dumps(previous))
    (tmp_path / 'ecs-candidate.json').write_text(json.dumps(current))
    monkeypatch.setattr(ecs, 'STATE_DIR', tmp_path)
    monkeypatch.setattr(ecs, 'STATE', state)
    monkeypatch.setattr(ecs, 'config', lambda: cfg)
    monkeypatch.setattr(ecs.sys, 'argv', ['ecs.py', 'rollback'])
    calls = []
    monkeypatch.setattr(ecs, 'aws', lambda *args: calls.append(args))
    monkeypatch.setattr(ecs, 'wait_services', lambda *args: None)
    monkeypatch.setattr(ecs, 'smoke', lambda *args: None)
    ecs.main()
    assert calls[0][-1] == 'previous'
    assert json.loads(state.read_text())['definitions'] == previous['definitions']


def test_standalone_migration_prepares_candidate_before_run(tmp_path, monkeypatch):
    import json
    cfg = CFG | {'account': '123456789012', 'repository': 'registry/repo'}
    monkeypatch.setattr(ecs, 'STATE_DIR', tmp_path)
    monkeypatch.setattr(ecs, 'STATE', tmp_path / 'ecs-last-good.json')
    monkeypatch.setattr(ecs, 'config', lambda: cfg)
    monkeypatch.setattr(ecs.sys, 'argv', ['ecs.py', 'migrate'])
    monkeypatch.setenv('RELEASE_ID', 'fixture-release')
    (tmp_path / 'ecs-image-fixture-release.json').write_text(json.dumps({'image': 'registry/repo@sha256:123'}))
    monkeypatch.setattr(ecs, 'definition', lambda cfg, role, image: 'candidate-' + role)
    calls = []
    monkeypatch.setattr(ecs, 'one_off', lambda *args: calls.append(args))
    ecs.main()
    assert json.loads((tmp_path / 'ecs-candidate.json').read_text())['definitions'] == {'api': 'candidate-api'}
    assert calls[0][1:3] == ('candidate-api', ['python', '-m', 'app.migrate'])


def test_maintenance_schedule_preserves_network_and_changes_release(monkeypatch):
    import json
    calls=[]
    record={'Name':'maintenance','Arn':'read-only','CreationDate':'read-only','State':'ENABLED',
        'ScheduleExpression':'rate(5 minutes)','FlexibleTimeWindow':{'Mode':'OFF'},
        'Target':{'Arn':'cluster','RoleArn':'scheduler-role','EcsParameters':{'TaskDefinitionArn':'old','NetworkConfiguration':{'awsvpcConfiguration':{'Subnets':['private']}}}}}
    def aws(*args):
        calls.append(args)
        return record if args[1]=='get-schedule' else {}
    monkeypatch.setattr(ecs,'aws',aws)
    ecs.maintenance_schedule(CFG|{'maintenance':{'schedule':'maintenance'}},'new',True)
    body=json.loads(calls[-1][-1])
    assert body['State']=='ENABLED' and body['Target']['EcsParameters']['TaskDefinitionArn']=='new'
    assert body['Target']['EcsParameters']['NetworkConfiguration']['awsvpcConfiguration']['Subnets']==['private']
    assert 'Arn' not in body and 'CreationDate' not in body
