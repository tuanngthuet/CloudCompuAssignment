param()

$ErrorActionPreference = 'Stop'
$account = '123456789012'
$azA = 'ap-southeast-2a'; $azB = 'ap-southeast-2b'
$idA = 'i-aaaaaaaa'; $idB = 'i-bbbbbbbb'
$idC = 'i-cccccccc'; $ciA = 'arn:ci:a'; $ciB = 'arn:ci:b'; $ciC = 'arn:ci:c'
$global:fragmentedSlots = $false
$global:useEc2EniFallback = $false
$global:fixtureServices = @(
    @{ serviceName = 'labseat-lab-api'; desiredCount = 2; runningCount = 2; pendingCount = 0; deployments = @(@{status='PRIMARY'}); placementConstraints = @(); capacityProviderStrategy=@(@{capacityProvider='labseat-lab'}); networkConfiguration=@{awsvpcConfiguration=@{subnets=@('subnet-a','subnet-b')}}; loadBalancers=@(@{targetGroupArn='arn:tg:local'}) },
    @{ serviceName = 'labseat-lab-worker'; desiredCount = 1; runningCount = 1; pendingCount = 0; deployments = @(@{status='PRIMARY'}); placementConstraints = @(); capacityProviderStrategy=@(@{capacityProvider='labseat-lab'}); networkConfiguration=@{awsvpcConfiguration=@{subnets=@('subnet-a','subnet-b')}} },
    @{ serviceName = 'labseat-lab-publisher'; desiredCount = 1; runningCount = 1; pendingCount = 0; deployments = @(@{status='PRIMARY'}); placementConstraints = @(); capacityProviderStrategy=@(@{capacityProvider='labseat-lab'}); networkConfiguration=@{awsvpcConfiguration=@{subnets=@('subnet-a','subnet-b')}} }
)
function aws {
    $global:LASTEXITCODE = 0
    $key = "$($args[0]) $($args[1])"
    $result = switch ($key) {
        'sts get-caller-identity' { @{ Account = $account } }
        'autoscaling describe-auto-scaling-groups' { @{ AutoScalingGroups = @(@{
            AutoScalingGroupName = 'labseat-lab-app'; AutoScalingGroupARN='arn:asg:local'; VPCZoneIdentifier = 'subnet-a,subnet-b'
            DesiredCapacity = 2; MaxSize = 6; SuspendedProcesses = @()
            Instances = if ($global:fragmentedSlots) { @(@{InstanceId=$idA;LifecycleState='InService';HealthStatus='Healthy'},@{InstanceId=$idB;LifecycleState='InService';HealthStatus='Healthy'},@{InstanceId=$idC;LifecycleState='InService';HealthStatus='Healthy'}) } else { @(@{InstanceId=$idA;LifecycleState='InService';HealthStatus='Healthy'},@{InstanceId=$idB;LifecycleState='InService';HealthStatus='Healthy'}) }
        }) } }
        'ecs describe-services' { @{ services = $global:fixtureServices; failures = @() } }
        'ecs describe-capacity-providers' { @{ capacityProviders = @(@{name='labseat-lab';autoScalingGroupProvider=@{autoScalingGroupArn='arn:asg:local'}}) } }
        'ecs list-container-instances' { @{ containerInstanceArns = if ($global:fragmentedSlots) { @($ciA,$ciB,$ciC) } else { @($ciA,$ciB) } } }
        'ecs describe-container-instances' { @{ containerInstances = @(
            @{containerInstanceArn=$ciA;ec2InstanceId=$idA;status='ACTIVE';agentConnected=$true;remainingResources=if ($global:useEc2EniFallback) { @(@{name='CPU';integerValue=512},@{name='MEMORY';integerValue=1024}) } else { @(@{name='CPU';integerValue=512},@{name='MEMORY';integerValue=1024},@{name='ENI';integerValue=1}) }},
            @{containerInstanceArn=$ciB;ec2InstanceId=$idB;status='ACTIVE';agentConnected=$true;remainingResources=if ($global:useEc2EniFallback) { @(@{name='CPU';integerValue=1024},@{name='MEMORY';integerValue=2048}) } elseif ($global:fragmentedSlots) { @(@{name='CPU';integerValue=128},@{name='MEMORY';integerValue=256},@{name='ENI';integerValue=1}) } else { @(@{name='CPU';integerValue=1024},@{name='MEMORY';integerValue=2048},@{name='ENI';integerValue=2}) }}
            if ($global:fragmentedSlots) { @{containerInstanceArn=$ciC;ec2InstanceId=$idC;status='ACTIVE';agentConnected=$true;remainingResources=@(@{name='CPU';integerValue=128},@{name='MEMORY';integerValue=256},@{name='ENI';integerValue=1})} }
        ) } }
        'ecs list-tasks' {
            $name = $args[[array]::IndexOf($args, '--service-name') + 1]
            @{ taskArns = switch ($name) { 'labseat-lab-api' { @('arn:task:api-a','arn:task:api-b') }; 'labseat-lab-worker' { @('arn:task:worker') }; 'labseat-lab-publisher' { @('arn:task:publisher') } } }
        }
        'ecs describe-tasks' { @{ tasks = @(
            @{taskArn='arn:task:api-a';containerInstanceArn=$ciA;group='service:labseat-lab-api';cpu='256';memory='512';attachments=@(@{details=@(@{name='privateIPv4Address';value='10.0.1.10'})})},
            @{taskArn='arn:task:api-b';containerInstanceArn=$ciB;group='service:labseat-lab-api';cpu='256';memory='512';attachments=@(@{details=@(@{name='privateIPv4Address';value='10.0.2.10'})})},
            @{taskArn='arn:task:worker';containerInstanceArn=$ciB;group='service:labseat-lab-worker';cpu='256';memory='512'},
            @{taskArn='arn:task:publisher';containerInstanceArn=$ciB;group='service:labseat-lab-publisher';cpu='256';memory='512'}
        ) } }
        'ec2 describe-instances' { @{ Reservations = @(@{ Instances = @(
            @{InstanceId=$idA;InstanceType='t3.small';NetworkInterfaces=@(@{NetworkInterfaceId='eni-a1'},@{NetworkInterfaceId='eni-a2'});Placement=@{AvailabilityZone=$azA};State=@{Name='running'}},
            @{InstanceId=$idB;InstanceType='t3.small';NetworkInterfaces=@(@{NetworkInterfaceId='eni-b1'},@{NetworkInterfaceId='eni-b2'});Placement=@{AvailabilityZone=$azB};State=@{Name='running'}}
            if ($global:fragmentedSlots) { @{InstanceId=$idC;InstanceType='t3.small';NetworkInterfaces=@(@{NetworkInterfaceId='eni-c1'});Placement=@{AvailabilityZone=$azB};State=@{Name='running'}} }
        ) }) } }
        'ec2 describe-instance-types' { @{ InstanceTypes = @(@{InstanceType='t3.small';NetworkInfo=@{MaximumNetworkInterfaces=3}}) } }
        'ec2 describe-subnets' { @{ Subnets = @(
            @{SubnetId='subnet-a';AvailabilityZone=$azA;AvailableIpAddressCount=100},
            @{SubnetId='subnet-b';AvailabilityZone=$azB;AvailableIpAddressCount=100}
        ) } }
        'elbv2 describe-target-health' { @{ TargetHealthDescriptions = @(
            @{Target=@{Id='10.0.1.10'};TargetHealth=@{State='healthy'}},@{Target=@{Id='10.0.2.10'};TargetHealth=@{State='healthy'}}
        ) } }
        default { throw "Unexpected fake AWS call: $key" }
    }
    return ($result | ConvertTo-Json -Depth 30 -Compress)
}

$run = '.local/assessment/c4-local-test-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
& (Join-Path $PSScriptRoot 'preflight.ps1') -Profile 'fake-local' -ExpectedAccount $account `
    -TargetAz $azA -TargetGroupArn 'arn:tg:local' -OutputDir $run | Out-Null
$baselinePath = Join-Path $run 'baseline.private.json'
$snapshot = Get-Content -LiteralPath $baselinePath -Raw -Encoding utf8 | ConvertFrom-Json
if ($snapshot.dry_run.target_instance_ids[0] -ne $idA -or
    $snapshot.dry_run.target_service_tasks.api -ne 1 -or
    $snapshot.gates.exact_survivor_slots -ne 'PASS' -or $snapshot.gates.survivor_api_overlap -ne 'PASS' -or
    $snapshot.gates.alb_api_az_coverage -ne 'PASS' -or
    $snapshot.gates.survivor_subnet_ips -ne 'PASS') { throw 'Local preflight fixture assertion failed' }
$global:fragmentedSlots = $true
$fragmentedRun = $run + '-fragmented'
& (Join-Path $PSScriptRoot 'preflight.ps1') -Profile 'fake-local' -ExpectedAccount $account `
    -TargetAz $azA -TargetGroupArn 'arn:tg:local' -OutputDir $fragmentedRun | Out-Null
$fragmented = Get-Content -LiteralPath (Join-Path $fragmentedRun 'baseline.private.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($fragmented.dry_run.survivor_remaining.cpu -lt 256 -or $fragmented.dry_run.survivor_remaining.memory -lt 512 -or
    $fragmented.gates.exact_survivor_slots -ne 'BLOCKED') { throw 'Fragmented per-instance slots falsely passed' }
$global:fragmentedSlots = $false
$global:useEc2EniFallback = $true
$eniRun = $run + '-ec2-eni'
& (Join-Path $PSScriptRoot 'preflight.ps1') -Profile 'fake-local' -ExpectedAccount $account `
    -TargetAz $azA -TargetGroupArn 'arn:tg:local' -OutputDir $eniRun | Out-Null
$eniSnapshot = Get-Content -LiteralPath (Join-Path $eniRun 'baseline.private.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($eniSnapshot.gates.exact_survivor_slots -ne 'PASS' -or $eniSnapshot.gates.survivor_api_overlap -ne 'BLOCKED' -or
    @($eniSnapshot.dry_run.survivor_slots | Where-Object eni_source -eq 'ec2_native_interface_limit_minus_attached').Count -ne 1) {
    throw 'EC2 native ENI fallback did not prove conservative free slot'
}
$global:useEc2EniFallback = $false
$attestationPath = Join-Path $run 'attestation.private.json'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'attestation.example.json') -Destination $attestationPath
$prepareBlocked = $false
try {
    & (Join-Path $PSScriptRoot 'prepare.ps1') -Profile 'fake-local' -ExpectedAccount $account `
        -BaselinePath $baselinePath -AttestationPath $attestationPath | Out-Null
} catch { Write-Output "Prepare guard: $($_.Exception.Message)"; $prepareBlocked = $_.Exception.Message -like '*Attestation/evidence missing*' }
if (-not $prepareBlocked) { throw 'Prepare did not reject missing attestation' }
$injectBlocked = $false
try {
    & (Join-Path $PSScriptRoot 'inject.ps1') -Profile 'fake-local' -ExpectedAccount $account `
        -BaselinePath $baselinePath -PreparedPath $baselinePath -AttestationPath $attestationPath `
        -ConfirmInstanceIds $idA | Out-Null
} catch { $injectBlocked = $_.Exception.Message -like '*Attestation/evidence missing*' }
if (-not $injectBlocked) { throw 'Inject did not reject missing attestation' }
$localAttest = Get-Content -LiteralPath $attestationPath -Raw -Encoding utf8 | ConvertFrom-Json
foreach ($property in @($localAttest.PSObject.Properties.Name | Where-Object { $_ -ne 'evidence' })) {
    $localAttest.$property = $true
    $localAttest.evidence.$property = 'local fake-AWS test only'
}
$localAttest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $attestationPath -Encoding utf8
& (Join-Path $PSScriptRoot 'prepare.ps1') -Profile 'fake-local' -ExpectedAccount $account `
    -BaselinePath $baselinePath -AttestationPath $attestationPath | Out-Null
$isolationBlocked = $false
try {
    & (Join-Path $PSScriptRoot 'inject.ps1') -Profile 'fake-local' -ExpectedAccount $account `
        -BaselinePath $baselinePath -PreparedPath $baselinePath -AttestationPath $attestationPath `
        -ConfirmInstanceIds $idA | Out-Null
} catch { $isolationBlocked = $_.Exception.Message -like '*not restricted to survivor*' }
if (-not $isolationBlocked) { throw 'Inject did not reject ASG spanning target AZ' }
& (Join-Path $PSScriptRoot 'rollback.ps1') -Profile 'fake-local' -ExpectedAccount $account `
    -BaselinePath $baselinePath | Out-Null
Write-Output 'C4 local fake-AWS: preflight PASS; attestation and ASG isolation guards PASS; prepare/rollback dry-runs PASS; no AWS network or mutation.'
