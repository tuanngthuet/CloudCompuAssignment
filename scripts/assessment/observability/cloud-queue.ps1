param(
 [ValidateSet('status','begin','disable','enable','finish','observe','cleanup-load-keys','cleanup-assets')][string]$Operation='status',
 [string]$Aws='aws',[string]$Profile='labseat',
 [string]$Run='c3-aws-mechanic-20261121'
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$directory=Join-Path $root ".local/assessment/$Run"
$scope=Get-Content (Join-Path $directory 'operator-scope.private.json') -Raw|ConvertFrom-Json
if($Run -ne 'c3-aws-mechanic-20261121' -or $scope.user_id -notlike 'labseat-c3-op-*'){throw 'Unexpected temporary operator scope'}
function Read-AwsJson {
 $result=& $Aws @args --profile $Profile --region ap-southeast-2 --output json --no-cli-pager
 if($LASTEXITCODE){throw 'AWS operation failed'}
 $result|ConvertFrom-Json
}
if((Read-AwsJson sts get-caller-identity).Account -ne '403030570855'){throw 'Wrong account'}
$group=(Read-AwsJson elasticache describe-user-groups --user-group-id $scope.user_group).UserGroups[0]
if($group.Status -ne 'active' -or $scope.user_id -notin $group.UserIds){throw 'Wait for the temporary operator group to become active'}
$api=(Read-AwsJson ecs describe-services --cluster labseat-lab --services labseat-lab-api).services[0]
$definition=(Read-AwsJson ecs describe-task-definition --task-definition $api.taskDefinition).taskDefinition
$app=$definition.containerDefinitions|Where-Object name -eq app
$secretEntries=@($app.secrets)+@(@{name='REDIS_OPERATOR_USERNAME';valueFrom=$scope.username_parameter},@{name='REDIS_OPERATOR_PASSWORD';valueFrom=$scope.password_parameter})
$source=@'
import json,os
from sqlalchemy.engine import make_url
url=make_url(os.environ['DATABASE_URL'])
assert url.host=='labseat-lab.cl2k6cgg0fdy.ap-southeast-2.rds.amazonaws.com'
os.environ['DATABASE_URL']=url.update_query_dict({'sslmode':'verify-full','sslrootcert':'/srv/labseat/app/infrastructure/database/rds-global-bundle.crt'}).render_as_string(hide_password=False)
from app.queue_admin import change
from app.infrastructure.redis.admission import client
assert client(operator=True).ping()
result=change('__OPERATION__',actor='person3-c3-mechanic',reason='User-authorized C3 queue window; preserve policy values and restore enabled baseline')
print('C3_QUEUE_POLICY='+json.dumps(result),flush=True)
'@
$source=$source.Replace('__OPERATION__',$Operation)
if($Operation -eq 'observe'){
 $source=$source.Substring(0,$source.IndexOf('result=change('))+@'
import time
from datetime import datetime,timezone
from sqlalchemy import text
from app.infrastructure.database.session import Session
from app.infrastructure.redis.admission import RedisQueue,policy
sid='3d7ca8f8-07fa-508e-abc7-3f0a7bf69d46'
redis=client(operator=True)
read_counts=redis.register_script("local t=redis.call('TIME');local n=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000);return {n,redis.call('ZCOUNT',KEYS[1],n-tonumber(ARGV[1]),'+inf'),redis.call('ZCOUNT',KEYS[2],'('..n,'+inf'),redis.call('ZCARD',KEYS[3])}")
for sample in range(240):
    with Session() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        p=policy(db)
        keys=RedisQueue.keys(p,sid)
        values=read_counts(keys=[keys[5],keys[3],keys[2]],args=[p.waiting_grace_seconds*1000])
        active=db.execute(text("SELECT count(*) FROM reservations WHERE session_id=CAST(:sid AS uuid) AND (status IN ('CONFIRMED','CHECKED_IN') OR (status='HELD' AND hold_expires_at>clock_timestamp()))"),{'sid':sid}).scalar_one()
        print('C3_QUEUE_SAMPLE='+json.dumps({'at_utc':datetime.now(timezone.utc).isoformat(),'redis_server_ms':values[0],'waiting_live':values[1],'admitted_live':values[2],'waiting_raw':values[3],'active_reservations':active,'capacity':p.capacity,'enabled':p.enabled}),flush=True)
    time.sleep(5)
print('C3_QUEUE_POLICY='+json.dumps(change('status')),flush=True)
'@
}
if($Operation -eq 'cleanup-load-keys'){
 $source=$source.Substring(0,$source.IndexOf('result=change('))+@'
from sqlalchemy import text
from uuid import uuid5,NAMESPACE_URL
from app.infrastructure.database.session import Session
from app.infrastructure.redis.admission import RedisQueue,policy
sid='3d7ca8f8-07fa-508e-abc7-3f0a7bf69d46'
with Session() as db:
    db.execute(text('SET TRANSACTION READ ONLY'))
    p=policy(db)
    assert p.enabled and not p.recovery_pending
    active=db.execute(text("SELECT count(*) FROM reservations WHERE session_id=CAST(:sid AS uuid) AND (status IN ('CONFIRMED','CHECKED_IN') OR (status='HELD' AND hold_expires_at>clock_timestamp()))"),{'sid':sid}).scalar_one()
    assert active==0,'Active trial reservations remain'
    known=[str(uuid5(NAMESPACE_URL,'labseat-isolated-load:demo-load-mechanic21:user-'+str(i))) for i in range(100)]
    script=client(operator=True).register_script("local t=redis.call('TIME');local n=tonumber(t[1])*1000+math.floor(tonumber(t[2])/1000);if redis.call('ZCOUNT',KEYS[3],'('..n,'+inf')>0 or redis.call('ZCOUNT',KEYS[5],n-tonumber(ARGV[1]),'+inf')>0 then return {-1,0} end;local total=redis.call('HLEN',KEYS[4]);local own=0;for i=2,#ARGV do if redis.call('HGET',KEYS[4],ARGV[i]) then own=own+1 end end;if own~=total then return {-2,total} end;return {redis.call('DEL',unpack(KEYS)),own}")
    cleaned=script(keys=RedisQueue.keys(p,sid)[1:],args=[p.waiting_grace_seconds*1000,*known])
    assert cleaned[0]>=0,'Live or foreign queue entries; cleanup refused'
    print('C3_QUEUE_CLEANUP='+json.dumps({'deleted_exact_load_keys':cleaned[0],'owned_entries':cleaned[1],'active_reservations':active,'global_ready_or_policy_modified':False}),flush=True)
print('C3_QUEUE_POLICY='+json.dumps(change('status')),flush=True)
'@
}
if($Operation -eq 'cleanup-assets'){
 $source=$source.Substring(0,$source.IndexOf('result=change('))+@'
import hashlib
from uuid import UUID,uuid5,NAMESPACE_URL
from sqlalchemy import select,func
from botocore.exceptions import ClientError
from app.models import Room,Event,StorageObject
from app.infrastructure.database.session import Session
from app.infrastructure.storage.objects import storage
from app.infrastructure.storage.registry import is_referenced
rid=UUID('ca17a86c-2c6a-5fc4-91f7-5e2c01cbaa64');eid=UUID('d3dd7bd8-d8de-5be2-a9aa-6ff6704ef361')
image='275a4fab45dc28ee77530d2ece6a7642f6f867565a444afbd212a32a3533f41b';poster='22b40371ad2246547bd4a33ebec323eee98652ce84119acf1e95ae3fd4906287'
owned=lambda name:uuid5(NAMESPACE_URL,'labseat-isolated-load:demo-load-mechanic21:'+name)
pairs=[(f'rooms/{rid}/maps/{owned("mechanic-image-"+image)}.png',image),(f'events/{eid}/poster/{owned("mechanic-poster-"+poster)}.jpg',poster)]
backend=storage();deleted=0;absent=0
with Session.begin() as db:
    assert db.get(Room,rid) is None and db.get(Event,eid) is None,'Remove exact trial fixture before assets'
    for key,expected in pairs:
        row=db.scalar(select(StorageObject).where(StorageObject.key==key).with_for_update())
        assert row is not None and not is_referenced(db,key),'Referenced/untracked object; cleanup refused'
        try:body=backend.get(key)
        except ClientError as exc:
            if exc.response['Error']['Code'] not in ('NoSuchKey','404'):raise
            absent+=1
        else:
            assert hashlib.sha256(body).hexdigest()==expected,'Trial object hash changed'
            backend.delete(key);deleted+=1
        row.state='DELETED';row.deleted_at=db.scalar(select(func.clock_timestamp()));row.quarantine_at=None
print('C3_ASSET_CLEANUP='+json.dumps({'owned_current_objects_deleted':deleted,'already_absent':absent,'registry_rows':2,'referenced_demo_objects_modified':0,'historical_versions_purged':False}),flush=True)
print('C3_QUEUE_POLICY='+json.dumps(change('status')),flush=True)
'@
}
if($Operation -in @('status','enable','finish')){
 $source+=[Environment]::NewLine+@'
from datetime import datetime,timezone
from sqlalchemy import text
from app.infrastructure.database.session import Session
with Session() as db:
    db.execute(text('SET TRANSACTION READ ONLY'))
    args={'sid':'3d7ca8f8-07fa-508e-abc7-3f0a7bf69d46'}
    jobs=db.execute(text("SELECT j.status,count(*) AS count,coalesce(sum(j.attempts),0) AS attempts,count(j.provider_message_id) AS provider_ids FROM email_jobs j JOIN reservations r ON r.id=j.reservation_id WHERE r.session_id=CAST(:sid AS uuid) GROUP BY j.status"),args).mappings().all()
    deliveries=db.execute(text("SELECT d.status,count(*) AS count,count(d.provider_message_id) AS provider_ids FROM notification_deliveries d JOIN reservations r ON r.id=d.reservation_id WHERE r.session_id=CAST(:sid AS uuid) GROUP BY d.status"),args).mappings().all()
    active=db.execute(text("SELECT status,count(*) AS count FROM reservations WHERE session_id=CAST(:sid AS uuid) GROUP BY status"),args).mappings().all()
    print('C3_QUEUE_POSTCHECK='+json.dumps({'at_utc':datetime.now(timezone.utc).isoformat(),'jobs':[dict(x) for x in jobs],'deliveries':[dict(x) for x in deliveries],'reservations':[dict(x) for x in active]},default=int),flush=True)
'@
}
$log=$app.logConfiguration.PSObject.Copy();$log.options.'awslogs-stream-prefix'='assessment-queue'
$candidate=@{family='labseat-assessment-queue-operator';networkMode='awsvpc';requiresCompatibilities=@('FARGATE');cpu='256';memory='512';executionRoleArn=$definition.executionRoleArn;taskRoleArn=$definition.taskRoleArn;runtimePlatform=@{cpuArchitecture='X86_64';operatingSystemFamily='LINUX'};containerDefinitions=@(@{name='operator';image=$app.image;essential=$true;cpu=256;memory=512;command=@('python','-c',$source);environment=$app.environment;secrets=$secretEntries;logConfiguration=$log;stopTimeout=60})}
$id='queue-'+$Operation+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
$file=Join-Path $directory ($id+'-definition.private.json');$candidate|ConvertTo-Json -Depth 30|Set-Content -Encoding UTF8 $file
$registered=(Read-AwsJson ecs register-task-definition --cli-input-json "file://$file").taskDefinition
$request=@{cluster='labseat-lab';taskDefinition=$registered.taskDefinitionArn;count=1;startedBy=$Run;launchType='FARGATE';platformVersion='1.4.0';networkConfiguration=$api.networkConfiguration;tags=@(@{key='assessment-run';value=$Run})}
$file=Join-Path $directory ($id+'-request.private.json');$request|ConvertTo-Json -Depth 20|Set-Content -Encoding UTF8 $file
$launch=Read-AwsJson ecs run-task --cli-input-json "file://$file"
if($launch.failures.Count -or $launch.tasks.Count -ne 1){throw 'Operator task not accepted'}
$task=$launch.tasks[0].taskArn
@{id=$id;task_arn=$task;task_definition=$registered.taskDefinitionArn;operation=$Operation;created_at_utc=[datetime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -Encoding UTF8 (Join-Path $directory ($id+'-operator-receipt.private.json'))
Write-Output "Queue operator $Operation started on Fargate"
if($Operation -eq 'observe'){
 $deadline=[datetime]::UtcNow.AddMinutes(25)
 do{
  $observed=(Read-AwsJson ecs describe-tasks --cluster labseat-lab --tasks $task).tasks[0]
  if($observed.lastStatus -eq 'STOPPED'){break}
  if([datetime]::UtcNow -ge $deadline){throw 'Observer exceeded 25 minutes; inspect original task before retry'}
  Start-Sleep -Seconds 15
 }while($true)
}else{
 & $Aws ecs wait tasks-stopped --cluster labseat-lab --tasks $task --profile $Profile --region ap-southeast-2 --no-cli-pager
 if($LASTEXITCODE){throw 'Inspect operator task before retry'}
}
$state=(Read-AwsJson ecs describe-tasks --cluster labseat-lab --tasks $task).tasks[0]
$stream=$log.options.'awslogs-stream-prefix'+'/operator/'+$task.Split('/')[-1]
$messages=(Read-AwsJson logs get-log-events --log-group-name $log.options.'awslogs-group' --log-stream-name $stream --start-from-head).events.message
$messages|ConvertTo-Json -Depth 6|Set-Content -Encoding UTF8 (Join-Path $directory ($id+'-log.private.json'))
if($state.containers[0].exitCode -ne 0){throw 'Operator failed; inspect private log'}
$policy=@($messages|Where-Object { $_.StartsWith('C3_QUEUE_POLICY=') })
if($policy.Count -ne 1){throw 'Missing policy result'}
$json=$policy[0].Substring('C3_QUEUE_POLICY='.Length)
[IO.File]::WriteAllText((Join-Path $directory ($id+'-policy.private.json')),$json)
if($Operation -eq 'status' -and -not (Test-Path (Join-Path $directory 'queue-baseline.private.json'))){[IO.File]::WriteAllText((Join-Path $directory 'queue-baseline.private.json'),$json)}
Write-Output "Queue $Operation completed; policy audit saved"
