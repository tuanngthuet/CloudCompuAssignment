param(
    [Parameter(Mandatory)][ValidateSet('prepare','sessions','verify','cleanup','smoke','physics-map','mechanic-map')][string]$Stage,
    [string]$Batch='demo-load-mechanic21',
    [string]$Aws='aws',
    [string]$Profile='labseat',
    [string]$Region='ap-southeast-2',
    [string]$ExpectedAccount='403030570855',
    [int]$TunnelPort=15432,
    [string]$CloseAt='2026-11-24T00:00:00+07:00',
    [int]$MinimumValidSeconds=14400,
    [string]$ManifestId,
    [switch]$Execute
)
$ErrorActionPreference='Stop'
if($Batch -notmatch '^demo-load-[a-z0-9-]{6,24}$'){throw 'Use an isolated demo-load-* batch'}
if($Region -ne 'ap-southeast-2'){throw 'Unexpected region'}
$root=(Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$directory=Join-Path $root ".local/assessment/$Batch"
if(-not (Test-Path -LiteralPath (Join-Path $directory 'backup-manifest.private.json'))){throw 'Verified demo backup is required first'}
if(-not $Execute -and $Stage -in @('prepare','sessions','physics-map','mechanic-map')){Write-Output "Plan only: $Stage isolated batch=$Batch; no AWS data change";return}
if($Execute -and $Stage -in @('prepare','sessions','physics-map','mechanic-map')){
    [IO.File]::WriteAllText((Join-Path $directory 'handoff-status.private.json'),(@{ready=$false;reason="Revalidate handoff after $Stage"}|ConvertTo-Json))
}
$account=& $Aws sts get-caller-identity --profile $Profile --region $Region --query Account --output text --no-cli-pager
if($LASTEXITCODE -or $account -ne $ExpectedAccount){throw 'Unexpected AWS identity'}
if($Stage -eq 'smoke' -and $Execute){
    $worker=(& $Aws ecs describe-services --cluster labseat-lab --services labseat-lab-worker --profile $Profile --region $Region --output json --no-cli-pager|ConvertFrom-Json).services[0]
    $workerDefinition=(& $Aws ecs describe-task-definition --task-definition $worker.taskDefinition --profile $Profile --region $Region --output json --no-cli-pager|ConvertFrom-Json).taskDefinition
    $backend=($workerDefinition.containerDefinitions.environment|Where-Object name -eq EMAIL_BACKEND).value
    if($LASTEXITCODE -or $backend -ne 'disabled' -or $worker.runningCount -lt 1 -or $worker.runningCount -ne $worker.desiredCount -or $worker.pendingCount -ne 0 -or $worker.deployments.Count -ne 1 -or $worker.deployments[0].rolloutState -ne 'COMPLETED'){throw 'Worker email-disabled rollout must be stable before smoke confirmation'}
}
$parameter=& $Aws ssm get-parameter --name /labseat/lab/DATABASE_URL --with-decryption --profile $Profile --region $Region --query Parameter.Value --output text --no-cli-pager
if($LASTEXITCODE){throw 'Database parameter lookup failed'}
$arguments=@($Stage,'--batch',$Batch,'--backup','/out/backup-manifest.private.json','--output','/out/load','--minimum-valid-seconds',"$MinimumValidSeconds")
if($Execute){$arguments+='--execute'}
if($Stage -eq 'prepare'){$arguments+=@('--close-at',$CloseAt)}
if($Stage -eq 'cleanup'){
    if(-not $ManifestId){throw 'Cleanup requires the exact manifest ID'}
    $arguments+=@('--manifest-id',$ManifestId)
}
$bootstrap=@'
import sys,json,os,socket
from sqlalchemy.engine import make_url
value=json.loads(sys.stdin.readline())
url=make_url(value['url'])
backup=json.load(open('/out/backup-manifest.private.json'))
assert url.host==backup['expected_host'] and url.host.endswith('.ap-southeast-2.rds.amazonaws.com')
url=url.set(port=value['port']).update_query_dict({'hostaddr':socket.gethostbyname('host.docker.internal'),'sslrootcert':'/srv/labseat/app/infrastructure/database/rds-global-bundle.crt','sslmode':'verify-full'})
os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
sys.path.insert(0,'/scripts/assessment/data')
from isolated_load import main
sys.argv=['isolated_load',*sys.argv[1:]]
main()
'@
try {
    (@{url=$parameter;port=$TunnelPort}|ConvertTo-Json -Compress)|docker run -i --rm -e APP_ENV=production -e EMAIL_BACKEND=disabled -e PYTHONPATH=/srv/labseat -e ASSESSMENT_PRIVATE_OUTPUT_ROOT=/out --mount "type=bind,source=$root/app,target=/srv/labseat/app,readonly" --mount "type=bind,source=$root/scripts,target=/scripts,readonly" --mount "type=bind,source=$directory,target=/out" labseat-assessment-b1b2:local python -c $bootstrap @arguments
    if($LASTEXITCODE){throw 'Isolated load operation failed; inspect before retrying'}
}finally{Remove-Variable parameter -ErrorAction SilentlyContinue}
if($Stage -eq 'smoke' -and $Execute){
    $load=Join-Path $directory 'load'
    $manifestFile=Join-Path $load 'manifest.json'
    $manifest=Get-Content -LiteralPath $manifestFile -Raw|ConvertFrom-Json
    $expiry=if($manifest.sessions_expire_at -is [datetime]){$manifest.sessions_expire_at.ToString('o')}else{[string]$manifest.sessions_expire_at}
    if($manifest.mapping.Count -ne 100){throw 'Expected explicit mapping for all 100 identities'}
    [IO.File]::WriteAllText($manifestFile,($manifest|ConvertTo-Json -Depth 15))
    $handoff=Join-Path $directory 'handoff'
    New-Item -ItemType Directory -Path $handoff -Force|Out-Null
    foreach($file in @('manifest.json','synthetic-sessions.json','smoke-result.json')){Copy-Item -LiteralPath (Join-Path $load $file) -Destination (Join-Path $handoff $file) -Force}
    $readme=@"
Private handoff for Person 3 — $Batch
BASE_URL=https://labseat.id.vn
SESSION_ID=$($manifest.load_session)
SESSIONS_FILE=<absolute path to synthetic-sessions.json>
Expiry: $expiry. Do not run after this expiry.
manifest.mapping links each zero-based session index to its user/event/schedule/room/seat.
Read smoke-result.json. Before the actual measurement, check 100 /me identities and readiness again.
Check the actual queue policy before each phase. platform.js consumes SESSIONS_FILE and requires the coordinated admission-off window. booking.js consumes this session file with REQUIRE_QUEUE_ENABLED=1 for admission tests; ACCOUNTS_FILE remains its optional login mode. This handoff does not change the global queue policy or start a load test.
If sessions expire or seats are occupied, ask Person 2 to verify the batch and regenerate sessions followed by smoke. Never edit expiry values manually.
Do not commit, publish, log, or attach these cookies/CSRF tokens to the report. No backup key or account master is included.
Tell Person 2 when measurement has stopped so the exact batch can be cleaned and demo data checked.
"@
    [IO.File]::WriteAllText((Join-Path $handoff 'README.txt'),$readme)
    $archive=Join-Path $directory 'handoff-person3.zip'
    Compress-Archive -LiteralPath @((Join-Path $handoff 'manifest.json'),(Join-Path $handoff 'synthetic-sessions.json'),(Join-Path $handoff 'smoke-result.json'),(Join-Path $handoff 'README.txt')) -DestinationPath $archive -Force
    $status=@{ready=$true;batch=$Batch;zip_sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant();files=@('manifest.json','synthetic-sessions.json','smoke-result.json','README.txt');expires_at=$expiry;recipient_acknowledged=$false;post_load_cleanup_performed=$false}
    [IO.File]::WriteAllText((Join-Path $directory 'handoff-status.private.json'),($status|ConvertTo-Json -Depth 5))
    "Private handoff prepared: $archive; expires=$expiry"
}
