param(
    [Parameter(Mandatory)][ValidateSet('prepare', 'book', 'restyle', 'rename', 'hsa', 'ielts', 'tsa', 'sat', 'hsa05', 'hsa05-map', 'hsa05-house-a', 'toeic', 'bio', 'bio-map', 'com', 'elec', 'mechanic', 'physics', 'chemistry')][string]$Stage,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9-]{2,23}$')][string]$Batch,
    [string]$Aws = 'aws',
    [string]$Profile = 'labseat',
    [string]$Region = 'ap-southeast-2',
    [string]$Cluster = 'labseat-lab',
    [Parameter(Mandatory)][string]$ExpectedAccount,
    [string]$HsaMap,
    [string]$HsaLogo,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$source = Join-Path $root 'app/assessment_seed.py'
$digest = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
$posterStages = @('hsa', 'ielts', 'tsa', 'sat', 'hsa05', 'toeic', 'bio', 'com', 'elec', 'mechanic', 'physics', 'chemistry')
$mapStages = $posterStages + @('hsa05-map', 'hsa05-house-a', 'bio-map')
if ($Stage -in $mapStages -and -not $HsaMap) { throw 'Exam artwork needs -HsaMap' }
if ($Stage -in $posterStages -and -not $HsaLogo) { throw 'Exam artwork needs -HsaLogo' }
if (-not $Execute) {
    Write-Output "Plan only: $Stage batch=$Batch cluster=$Cluster source=$digest"
    return
}

function Read-AwsJson {
    $result = & $Aws @args --profile $Profile --region $Region --no-cli-pager --output json
    if ($LASTEXITCODE) { throw "AWS failed: $($args[0]) $($args[1])" }
    $result | ConvertFrom-Json
}

$identity = Read-AwsJson sts get-caller-identity
if ($identity.Account -ne $ExpectedAccount) { throw 'Unexpected AWS account' }
$services = (Read-AwsJson ecs describe-services --cluster $Cluster --services "$Cluster-api" "$Cluster-worker").services
$api = $services | Where-Object serviceName -eq "$Cluster-api"
$worker = $services | Where-Object serviceName -eq "$Cluster-worker"
if (-not $api -or -not $worker) { throw 'Expected API and worker services' }
if ($Stage -eq 'book') {
    $workerDefinition = (Read-AwsJson ecs describe-task-definition --task-definition $worker.taskDefinition).taskDefinition
    $backend = ($workerDefinition.containerDefinitions.environment | Where-Object name -eq 'EMAIL_BACKEND').value
    if ($worker.deployments.Count -ne 1 -or $worker.deployments[0].rolloutState -ne 'COMPLETED' -or
        $worker.runningCount -ne $worker.desiredCount -or $worker.runningCount -lt 1 -or $backend -ne 'disabled') {
        throw 'Worker disabled rollout must be complete before synthetic bookings'
    }
}
$definition = (Read-AwsJson ecs describe-task-definition --task-definition $api.taskDefinition).taskDefinition
$container = $definition.containerDefinitions | Where-Object name -eq 'app'
$bucket = ($container.environment | Where-Object name -eq 'S3_BUCKET').value
$prefix = ($container.environment | Where-Object name -eq 'S3_PREFIX').value
if (-not $bucket) { throw 'Expected private S3 backing store' }
$privateDir = Join-Path $root ".local/assessment/$Batch"
New-Item -ItemType Directory -Path $privateDir -Force | Out-Null
$privateKey = Join-Path $privateDir 'seed-transport.pem'
$publicKey = ''
if ($Stage -eq 'prepare') {
    if (-not (Test-Path -LiteralPath $privateKey)) {
        & openssl genpkey -quiet -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out $privateKey
        if ($LASTEXITCODE) { throw 'Unable to create private transport key' }
    }
    $publicKey = (& openssl pkey -in $privateKey -pubout) -join "`n"
    if ($LASTEXITCODE) { throw 'Unable to derive public transport key' }
}

# No credentials are passed in ECS overrides. The prepare task emits only RSA
# ciphertext for the random seed master. The operator retains the private key.
$launcher = @'
import base64, hashlib, os, secrets, subprocess, sys, tempfile
from pathlib import Path
from app.infrastructure.storage.objects import storage
path, digest, batch, stage, public_key = sys.argv[1:]
source = storage().get(path)
if hashlib.sha256(source).hexdigest() != digest:
    raise RuntimeError("Assessment source digest mismatch")
module = {"__name__": "assessment_seed"}
exec(compile(source, "assessment_seed.py", "exec"), module)
sys.argv = ["assessment_seed", stage, "--batch", batch, "--execute"]
if stage == "prepare":
    with module["Session"].begin() as db:
        batch_row = module["Batch"](batch)
        module["lock_batch"](db, batch_row)
        if db.get(module["User"], batch_row.user_ids[0]):
            raise RuntimeError("Batch exists; use the encrypted master from the first successful task")
        master = secrets.token_urlsafe(48)
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "public.pem"
            key.write_text(public_key + "\n")
            encrypted = subprocess.run(
                ["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", str(key),
                 "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
                input=master.encode(), capture_output=True, check=True,
            ).stdout
        print("ASSESSMENT_ENCRYPTED_MASTER=" + base64.b64encode(encrypted).decode(), flush=True)
        clock = module["booking"].now(db)
        module["assert_owned"](db, batch_row)
        module["add_users"](db, batch_row, master, clock)
        module["add_catalogue"](db, batch_row, clock)
    print("ASSESSMENT_PREPARE_COMMITTED", flush=True)
else:
    if stage == "book":
        sys.argv.append("--email-window-confirmed")
    module["main"]()
'@

$bundleFile = $null
if ($Stage -in $mapStages) {
    $bundleFile = Join-Path ([IO.Path]::GetTempPath()) ("labseat-hsa-" + [guid]::NewGuid() + ".py")
    $map64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $HsaMap).Path))
    $logo64 = if ($HsaLogo) { [Convert]::ToBase64String([IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $HsaLogo).Path)) } else { '' }
    [IO.File]::WriteAllText($bundleFile, ([IO.File]::ReadAllText($source) +
        "`nfrom base64 import b64decode`nHSA_MAP = b64decode('$map64')`nHSA_LOGO = b64decode('$logo64')`n"))
    $source = $bundleFile
    $digest = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
}
$key = "rooms/assessment-code/$Batch/$digest.py"
$objectKey = if ($prefix) { "$($prefix.TrimEnd('/'))/$key" } else { $key }
try {
    $upload = Read-AwsJson s3api put-object --bucket $bucket --key $objectKey --body $source --server-side-encryption AES256
} finally {
    if ($bundleFile -and (Test-Path -LiteralPath $bundleFile)) { Remove-Item -LiteralPath $bundleFile }
}
$runFile = Join-Path ([IO.Path]::GetTempPath()) ("labseat-assessment-" + [guid]::NewGuid() + ".json")
$taskStopped = $true
try {
    $request = @{
        cluster = $Cluster
        taskDefinition = $api.taskDefinition
        count = 1
        startedBy = "assessment-$Batch"
        capacityProviderStrategy = $api.capacityProviderStrategy
        networkConfiguration = $api.networkConfiguration
        overrides = @{containerOverrides = @(@{
            name = 'app'
            command = @('python', '-c', $launcher, $key, $digest, $Batch, $Stage, $publicKey)
        })}
    }
    [IO.File]::WriteAllText($runFile, ($request | ConvertTo-Json -Depth 25 -Compress))
    $result = Read-AwsJson ecs run-task --cli-input-json "file://$runFile"
    if ($result.failures.Count -or $result.tasks.Count -ne 1) { throw 'ECS did not accept one assessment task' }
    $task = $result.tasks[0].taskArn
    $taskStopped = $false
    Write-Output "Started $task"
    & $Aws ecs wait tasks-stopped --cluster $Cluster --tasks $task --profile $Profile --region $Region --no-cli-pager
    if ($LASTEXITCODE) { throw "Unable to wait for $task; inspect the task before retrying" }
    $taskStopped = $true
    $stopped = (Read-AwsJson ecs describe-tasks --cluster $Cluster --tasks $task).tasks[0]
    $exitCode = ($stopped.containers | Where-Object name -eq 'app').exitCode
    if ($null -eq $exitCode -or $exitCode -ne 0) {
        throw "Task failed: $($stopped.stoppedReason), exit=$exitCode, task=$task"
    }
    if ($Stage -eq 'prepare') {
        $log = $container.logConfiguration.options
        $stream = "$($log.'awslogs-stream-prefix')/app/$($task.Split('/')[-1])"
        $messages = (Read-AwsJson logs get-log-events --log-group-name $log.'awslogs-group' --log-stream-name $stream --start-from-head).events.message
        $ciphertext = @($messages | Where-Object { $_ -like 'ASSESSMENT_ENCRYPTED_MASTER=*' })
        if ($ciphertext.Count -ne 1 -or 'ASSESSMENT_PREPARE_COMMITTED' -notin $messages) {
            throw "Missing commit or protected credential output for $task"
        }
        $sealed = Join-Path $privateDir 'seed-master.encrypted'
        [IO.File]::WriteAllBytes($sealed, [Convert]::FromBase64String(($ciphertext[0] -split '=', 2)[1]))
        & openssl pkeyutl -decrypt -inkey $privateKey -in $sealed -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -out (Join-Path $privateDir 'seed-master.txt')
        if ($LASTEXITCODE) { throw 'Could not decrypt the assessment master locally' }
    }
    Write-Output "Completed $Stage on $task"
} finally {
    if (Test-Path -LiteralPath $runFile) { Remove-Item -LiteralPath $runFile }
    $deleteArgs = @('s3api', 'delete-object', '--bucket', $bucket, '--key', $objectKey)
    if ($upload.VersionId) { $deleteArgs += @('--version-id', $upload.VersionId) }
    if ($taskStopped) {
        Read-AwsJson @deleteArgs | Out-Null
    } else {
        Write-Warning "Source staging remains until the task stops: $objectKey version=$($upload.VersionId)"
    }
}
