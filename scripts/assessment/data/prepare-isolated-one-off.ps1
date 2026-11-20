param([string]$Batch='demo-load-20261121a',[string]$Aws='aws',[string]$Profile='labseat',
      [string]$Region='ap-southeast-2',[string]$ExpectedAccount='403030570855',
      [string]$CloseAt='2026-11-24T00:00:00+07:00',[switch]$Execute)
$ErrorActionPreference='Stop'
$env:AWS_CLI_OUTPUT_ENCODING='UTF-8'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
if($Batch -notmatch '^demo-load-[a-z0-9-]{6,24}$'){throw 'Dedicated namespace required'}
$directory=Join-Path $root ".local/assessment/$Batch"
$backupFile=Join-Path $directory 'backup-manifest.private.json'
$backup=Get-Content -LiteralPath $backupFile -Raw|ConvertFrom-Json
if(-not $backup.verified -or -not $backup.assets_verified){throw 'Verified backup required first'}
if(-not $Execute){'Plan only: isolated load preparation in ECS/VPC; no change';return}
function Read-AwsJson {
    $value=& $Aws @args --profile $Profile --region $Region --output json --no-cli-pager
    if($LASTEXITCODE){throw 'AWS operation failed'}
    $value|ConvertFrom-Json
}
if((Read-AwsJson sts get-caller-identity).Account -ne $ExpectedAccount){throw 'Unexpected AWS account'}
$api=(Read-AwsJson ecs describe-services --cluster labseat-lab --services labseat-lab-api).services[0]
$definition=(Read-AwsJson ecs describe-task-definition --task-definition $api.taskDefinition).taskDefinition
$container=$definition.containerDefinitions|Where-Object name -eq app
$bucket=($container.environment|Where-Object name -eq S3_BUCKET).value
$prefix=($container.environment|Where-Object name -eq S3_PREFIX).value
if(-not $bucket -or $container.image -notmatch '@sha256:[a-f0-9]{64}$'){throw 'Pinned source image/private bucket required'}
$privateKey=Join-Path $directory 'load-transport.pem'
$rsa=[Security.Cryptography.RSA]::Create(3072)
try {
    if(Test-Path -LiteralPath $privateKey){$rsa.ImportFromPem([IO.File]::ReadAllText($privateKey))}
    else{[IO.File]::WriteAllText($privateKey,$rsa.ExportPkcs8PrivateKeyPem())}
    $public=$rsa.ExportSubjectPublicKeyInfoPem()
    $files=@{}
    foreach($entry in @(@('scripts/assessment/data/demo_backup.py','scripts/assessment/data/demo_backup.py'),
        @('scripts/assessment/data/isolated_load.py','scripts/assessment/data/isolated_load.py'),
        @('scripts/tests/db-invariants.sql','scripts/tests/db-invariants.sql'),
        @(".local/assessment/$Batch/backup-manifest.private.json",'out/backup-manifest.private.json'),
        @(".local/assessment/$Batch/source-fingerprint.json",'out/source-fingerprint.json'))){
        $files[$entry[1]]=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $root $entry[0])))
    }
    if($backup.demo_fingerprint){$files['out/'+$backup.demo_fingerprint]=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $directory $backup.demo_fingerprint)))}
    $payload=@{files=$files;batch=$Batch;close_at=$CloseAt;public_key=$public}|ConvertTo-Json -Depth 12 -Compress
    $payload64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
    $source=@'
import base64,json,os,sys,tempfile,secrets,subprocess
from pathlib import Path
p=json.loads(base64.b64decode('__PAYLOAD__'))
root=Path(tempfile.mkdtemp(prefix='labseat-protected-load-'))
for name,body in p['files'].items():
 path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(base64.b64decode(body))
sys.path.insert(0,str(root/'scripts/assessment/data'))
from sqlalchemy.engine import make_url
url=make_url(os.environ['DATABASE_URL'])
backup=json.loads((root/'out/backup-manifest.private.json').read_text())
assert url.host==backup['expected_host']
os.environ['DATABASE_URL']=url.update_query_dict({'sslmode':'verify-full','sslrootcert':'/srv/labseat/app/infrastructure/database/rds-global-bundle.crt'}).render_as_string(hide_password=False)
os.environ['ASSESSMENT_PRIVATE_OUTPUT_ROOT']=str(root/'out')
from isolated_load import Scope,main
from app.infrastructure.database.session import Session
from app.models import User
scope=Scope(p['batch'])
with Session() as db:
 if db.get(User,scope.users[0]):raise RuntimeError('Scope exists; verify/recover the original private handoff, do not rotate its master')
master=secrets.token_urlsafe(48)
public=root/'public.pem';public.write_text(p['public_key'])
sealed=subprocess.run(['openssl','pkeyutl','-encrypt','-pubin','-inkey',str(public),'-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256','-pkeyopt','rsa_mgf1_md:sha256'],input=master.encode(),capture_output=True,check=True).stdout
print('LOAD_ENCRYPTED_MASTER='+base64.b64encode(sealed).decode(),flush=True)
out=root/'out/load';out.mkdir()
(out/'load-master.txt').write_text(master)
sys.argv=['isolated_load','prepare','--batch',p['batch'],'--backup',str(root/'out/backup-manifest.private.json'),'--output',str(out),'--close-at',p['close_at'],'--execute']
main()
print('LOAD_PREPARED='+json.dumps(json.loads((out/'manifest.json').read_text())),flush=True)
'@
    $source=$source.Replace('__PAYLOAD__',$payload64).Replace("`r`n","`n")
    $bundle=Join-Path $directory 'prepare-source.private.py'
    [IO.File]::WriteAllText($bundle,$source)
    $digest=(Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
    $key="rooms/assessment-code/$Batch/$digest.py"
    $objectKey=if($prefix){$prefix.TrimEnd('/')+'/'+$key}else{$key}
    $upload=Read-AwsJson s3api put-object --bucket $bucket --key $objectKey --body $bundle --server-side-encryption AES256
    $launcher="import sys,hashlib;from app.infrastructure.storage.objects import storage;source=storage().get(sys.argv[1]);assert hashlib.sha256(source).hexdigest()==sys.argv[2];exec(compile(source,'protected_load.py','exec'),{'__name__':'__main__'})"
    $request=@{cluster='labseat-lab';taskDefinition=$api.taskDefinition;count=1;startedBy=$Batch;capacityProviderStrategy=$api.capacityProviderStrategy;networkConfiguration=$api.networkConfiguration;overrides=@{containerOverrides=@(@{name='app';command=@('python','-c',$launcher,$key,$digest)})}}
    $requestFile=Join-Path $directory 'prepare-task.private.json'
    [IO.File]::WriteAllText($requestFile,($request|ConvertTo-Json -Depth 25 -Compress))
    $stopped=$true
    try {
        $response=Read-AwsJson ecs run-task --cli-input-json "file://$requestFile"
        if($response.failures.Count -or $response.tasks.Count -ne 1){throw 'Prepare task not accepted'}
        $task=$response.tasks[0].taskArn;$stopped=$false
        $task|Set-Content (Join-Path $directory 'prepare-task.txt')
        Write-Output "Isolated prepare started in VPC: $task"
        & $Aws ecs wait tasks-stopped --cluster labseat-lab --tasks $task --profile $Profile --region $Region --no-cli-pager
        if($LASTEXITCODE){throw 'Wait failed; inspect task before retry'}
        $stopped=$true
        $state=(Read-AwsJson ecs describe-tasks --cluster labseat-lab --tasks $task).tasks[0]
        [IO.File]::WriteAllText((Join-Path $directory 'prepare-task-state.private.json'),($state|ConvertTo-Json -Depth 30))
        $log=$container.logConfiguration.options
        $stream=$log.'awslogs-stream-prefix'+'/app/'+$task.Split('/')[-1]
        $messages=(Read-AwsJson logs get-log-events --log-group-name $log.'awslogs-group' --log-stream-name $stream --start-from-head).events.message
        [IO.File]::WriteAllText((Join-Path $directory 'prepare-log.private.json'),($messages|ConvertTo-Json -Depth 4))
        if(($state.containers|Where-Object name -eq app).exitCode -ne 0){throw 'Prepare failed; inspect private log, do not retry blindly'}
        $sealed=@($messages|Where-Object {$_ -like 'LOAD_ENCRYPTED_MASTER=*'})
        $committed=@($messages|Where-Object {$_ -like 'LOAD_PREPARED=*'})
        if($sealed.Count -ne 1 -or $committed.Count -ne 1){throw 'Missing encrypted master or committed manifest'}
        $master=[Text.Encoding]::UTF8.GetString($rsa.Decrypt([Convert]::FromBase64String(($sealed[0]-split '=',2)[1]),[Security.Cryptography.RSAEncryptionPadding]::OaepSHA256))
        $out=Join-Path $directory 'load';New-Item -ItemType Directory -Path $out -Force|Out-Null
        [IO.File]::WriteAllText((Join-Path $out 'load-master.txt'),$master)
        [IO.File]::WriteAllText((Join-Path $out 'manifest.json'),($committed[0]-split '=',2)[1])
        'Prepare committed; private master recovered locally; no plaintext credential was logged.'
    }finally{
        if($stopped){$delete=@('s3api','delete-object','--bucket',$bucket,'--key',$objectKey);if($upload.VersionId){$delete+=@('--version-id',$upload.VersionId)};Read-AwsJson @delete|Out-Null}
    }
}finally{$rsa.Dispose();Remove-Variable master -ErrorAction SilentlyContinue}
