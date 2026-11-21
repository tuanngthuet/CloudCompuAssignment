param(
    [ValidateSet('Start','Collect')][string]$Stage='Start',
    [ValidateSet('preflight','baseline','platform','admission20','admission50','scaling60','scaling100','scaling150','scaling200','recovery')][string]$Phase='preflight',
    [string]$Batch='demo-load-mechanic21',
    [string]$Run='c3-aws-mechanic-20261121',
    [string]$Aws='aws',[string]$Profile='labseat',
    [string]$K6BinaryPath,
    [string]$Receipt
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
if($Batch -notmatch '^demo-load-[a-z0-9-]+$' -or $Run -notmatch '^c3-[a-z0-9-]+$'){throw 'Invalid private namespace'}
$directory=Join-Path $root ".local/assessment/$Run"
New-Item -ItemType Directory -Path $directory -Force|Out-Null
function Read-AwsJson {
    $value=& $Aws @args --profile $Profile --region ap-southeast-2 --output json --no-cli-pager
    if($LASTEXITCODE){throw 'AWS call failed'}
    $value|ConvertFrom-Json
}
if((Read-AwsJson sts get-caller-identity).Account -ne '403030570855'){throw 'Unexpected AWS account'}
if($Stage -eq 'Collect'){
    $record=Get-Content -LiteralPath $Receipt -Raw|ConvertFrom-Json
    if($record.run -ne $Run){throw 'Wrong receipt scope'}
    $task=(Read-AwsJson ecs describe-tasks --cluster labseat-lab --tasks $record.task_arn).tasks[0]
    if($task.lastStatus -ne 'STOPPED'){throw 'Task is still running; do not collect incomplete output'}
    $task|ConvertTo-Json -Depth 30|Set-Content -Encoding UTF8 (Join-Path $directory ($record.id+'-task.private.json'))
    $archive=Join-Path $directory ($record.id+'-result.tar.gz')
    $null=Read-AwsJson s3api get-object --bucket $record.bucket --key $record.result_object_key $archive
    $output=Join-Path $directory $record.id;New-Item -ItemType Directory -Path $output -Force|Out-Null
    & python -c 'import tarfile,sys; a=tarfile.open(sys.argv[1]); a.extractall(sys.argv[2],filter="data")' $archive $output
    if($LASTEXITCODE){throw 'Artifact extraction failed'}
    $result=Get-Content -LiteralPath (Join-Path $output 'run.json') -Raw|ConvertFrom-Json
    [pscustomobject]@{phase=$record.phase;result=$result.result;output=$output;clock=$result.clock;error=$result.error}|ConvertTo-Json -Depth 5
    return
}
$private=Join-Path $root ".local/assessment/$Batch"
$manifest=Get-Content -LiteralPath (Join-Path $private 'load/manifest.json') -Raw|ConvertFrom-Json
$smoke=Get-Content -LiteralPath (Join-Path $private 'load/smoke-result.json') -Raw|ConvertFrom-Json
if(-not $smoke.verified -or $manifest.capacity -ne 180 -or $manifest.mapping.Count -ne 100){throw 'Verified Mechanic handoff required'}
if($Phase -ne 'recovery'){
    $handoff=Get-Content -LiteralPath (Join-Path $private 'handoff-status.private.json') -Raw|ConvertFrom-Json
    if(-not $handoff.ready -or $handoff.batch -ne $Batch){throw 'Handoff retired or not ready; prepare and smoke a fresh fixture before load'}
}
if([datetimeoffset]::Parse($manifest.sessions_expire_at) -lt [datetimeoffset]::UtcNow.AddHours(2)){throw 'Refresh B2 sessions before load'}
if(-not $K6BinaryPath){$K6BinaryPath=Join-Path $directory 'k6'}
if(-not (Test-Path -LiteralPath $K6BinaryPath)){throw 'Supply the Linux k6 binary; no installation on application EC2'}
$services=(Read-AwsJson ecs describe-services --cluster labseat-lab --services labseat-lab-api labseat-lab-worker).services
$api=$services|Where-Object serviceName -eq labseat-lab-api
$worker=$services|Where-Object serviceName -eq labseat-lab-worker
$workerDef=(Read-AwsJson ecs describe-task-definition --task-definition $worker.taskDefinition).taskDefinition
if(($workerDef.containerDefinitions.environment|Where-Object name -eq EMAIL_BACKEND).value -ne 'disabled' -or $worker.runningCount -ne $worker.desiredCount -or $worker.pendingCount -or $worker.deployments.Count -ne 1 -or $worker.deployments[0].rolloutState -ne 'COMPLETED'){throw 'Email-disabled worker must be stable'}
$definition=(Read-AwsJson ecs describe-task-definition --task-definition $api.taskDefinition).taskDefinition
$app=$definition.containerDefinitions|Where-Object name -eq app
$bucket=($app.environment|Where-Object name -eq S3_BUCKET).value
$prefix=($app.environment|Where-Object name -eq S3_PREFIX).value
if(-not $bucket -or $app.image -notmatch '@sha256:[a-f0-9]{64}$'){throw 'Pinned approved image/private storage required'}
$bindings=@{k6=[IO.Path]::GetFullPath($K6BinaryPath);'manifest.json'=(Join-Path $private 'load/manifest.json');'sessions.json'=(Join-Path $private 'load/synthetic-sessions.json')}
foreach($file in @('catalogue.js','platform.js','booking.js','ecs-scaling.js')){$bindings[$file]=Join-Path $root "scripts/load/$file"}
$bindingFile=Join-Path $directory 'bundle-bindings.private.json';$bindings|ConvertTo-Json|Set-Content -Encoding UTF8 $bindingFile
$currentHashes=@{}
foreach($name in $bindings.Keys){$currentHashes[$name]=(Get-FileHash -LiteralPath $bindings[$name] -Algorithm SHA256).Hash.ToLowerInvariant()}
$cached=$null
foreach($previousFile in (Get-ChildItem -LiteralPath $directory -Filter '*-receipt.private.json' | Sort-Object LastWriteTime -Descending)){
    $previous=Get-Content -LiteralPath $previousFile.FullName -Raw|ConvertFrom-Json
    if(-not $previous.phase -or $previous.run -ne $Run -or $previous.bucket -ne $bucket){continue}
    $runFile=Join-Path $directory ($previous.id+'/run.json')
    if(-not (Test-Path -LiteralPath $runFile)){continue}
    $old=(Get-Content -LiteralPath $runFile -Raw|ConvertFrom-Json).input_hashes
    if(@($old.PSObject.Properties).Count -ne $currentHashes.Count){continue}
    $same=$true
    foreach($name in $currentHashes.Keys){if($old.$name -ne $currentHashes[$name]){$same=$false;break}}
    if($same){$cached=$previous;break}
}
$bundle=Join-Path $directory 'bundle.private.tar.gz'
if(-not $cached){
& python -c 'import json,tarfile,hashlib,io,sys,pathlib; files=json.load(open(sys.argv[1],encoding="utf-8-sig")); hashes={k:hashlib.sha256(pathlib.Path(v).read_bytes()).hexdigest() for k,v in files.items()}; a=tarfile.open(sys.argv[2],"w:gz"); [a.add(v,arcname=k) for k,v in files.items()]; data=json.dumps(hashes).encode(); t=tarfile.TarInfo("hashes.json"); t.size=len(data); a.addfile(t,io.BytesIO(data)); a.close()' $bindingFile $bundle
if($LASTEXITCODE){throw 'Bundle build failed'}
$bundleHash=(Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
$bundleKey="rooms/assessment-code/$Run/$bundleHash.tar.gz"
}else{
    $bundleHash=$cached.bundle_sha256
    $bundleKey="rooms/assessment-code/$Run/$bundleHash.tar.gz"
    Write-Output 'Reusing verified bundle: all input file hashes unchanged'
}
$source=Join-Path $PSScriptRoot 'cloud_runner.py';$sourceHash=(Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceKey="rooms/assessment-code/$Run/$sourceHash.py"
function Object-Key([string]$key){if($prefix){$prefix.TrimEnd('/')+'/'+$key}else{$key}}
if($cached){
    if($cached.bundle_object_key -ne (Object-Key $bundleKey)){throw 'Cached bundle outside expected scope'}
    $null=Read-AwsJson s3api head-object --bucket $bucket --key $cached.bundle_object_key --version-id $cached.bundle_version
    $bundleUpload=[pscustomobject]@{VersionId=$cached.bundle_version}
}else{
    $bundleUpload=Read-AwsJson s3api put-object --bucket $bucket --key (Object-Key $bundleKey) --body $bundle --server-side-encryption AES256
}
$sourceUpload=Read-AwsJson s3api put-object --bucket $bucket --key (Object-Key $sourceKey) --body $source --server-side-encryption AES256
$id=$Phase+'-'+[guid]::NewGuid().ToString('N').Substring(0,10)
$resultKey="rooms/assessment-code/$Run/$id-result.tar.gz"
$launcher='import os,hashlib;from app.infrastructure.storage.objects import storage;b=storage().get(os.environ["ASSESSMENT_CODE_KEY"]);assert hashlib.sha256(b).hexdigest()==os.environ["ASSESSMENT_CODE_SHA256"];exec(compile(b,"cloud_runner.py","exec"),{"__name__":"__main__"})'
$environment=@($app.environment|Where-Object {$_.name -in @('S3_BUCKET','S3_PREFIX','AWS_REGION','STORAGE_BACKEND')})
$environment+=@(@{name='ASSESSMENT_CODE_KEY';value=$sourceKey},@{name='ASSESSMENT_CODE_SHA256';value=$sourceHash},@{name='ASSESSMENT_BUNDLE_KEY';value=$bundleKey},@{name='ASSESSMENT_BUNDLE_SHA256';value=$bundleHash},@{name='ASSESSMENT_RESULT_KEY';value=$resultKey},@{name='ASSESSMENT_PHASE';value=$Phase})
$log=$app.logConfiguration.PSObject.Copy();$log.options.'awslogs-stream-prefix'='assessment-runner'
$candidate=@{family='labseat-assessment-load-runner';networkMode='awsvpc';requiresCompatibilities=@('FARGATE');cpu='2048';memory='4096';executionRoleArn=$definition.executionRoleArn;taskRoleArn=$definition.taskRoleArn;runtimePlatform=@{cpuArchitecture='X86_64';operatingSystemFamily='LINUX'};containerDefinitions=@(@{name='runner';image=$app.image;essential=$true;cpu=2048;memory=4096;command=@('python','-c',$launcher);environment=$environment;logConfiguration=$log;stopTimeout=120})}
$candidateFile=Join-Path $directory ($id+'-definition.private.json');$candidate|ConvertTo-Json -Depth 25|Set-Content -Encoding UTF8 $candidateFile
$registered=(Read-AwsJson ecs register-task-definition --cli-input-json "file://$candidateFile").taskDefinition
$request=@{cluster='labseat-lab';taskDefinition=$registered.taskDefinitionArn;count=1;startedBy=$Run;launchType='FARGATE';platformVersion='1.4.0';networkConfiguration=$api.networkConfiguration;tags=@(@{key='assessment-run';value=$Run},@{key='owner';value='person3-load'})}
$requestFile=Join-Path $directory ($id+'-request.private.json');$request|ConvertTo-Json -Depth 25|Set-Content -Encoding UTF8 $requestFile
$launched=Read-AwsJson ecs run-task --cli-input-json "file://$requestFile"
if($launched.failures.Count -or $launched.tasks.Count -ne 1){throw 'Fargate runner was not accepted'}
$receiptFile=Join-Path $directory ($id+'-receipt.private.json')
@{id=$id;run=$Run;phase=$Phase;task_arn=$launched.tasks[0].taskArn;task_definition=$registered.taskDefinitionArn;bucket=$bucket;result_key=$resultKey;result_object_key=(Object-Key $resultKey);bundle_object_key=(Object-Key $bundleKey);bundle_version=$bundleUpload.VersionId;source_object_key=(Object-Key $sourceKey);source_version=$sourceUpload.VersionId;source_sha256=$sourceHash;bundle_sha256=$bundleHash;created_at_utc=[datetime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 8|Set-Content -Encoding UTF8 $receiptFile
Write-Output "Fargate runner started for $Phase; receipt=$receiptFile"
