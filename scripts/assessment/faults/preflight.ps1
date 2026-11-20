param(
    [Parameter(Mandatory)][string]$Profile,
    [Parameter(Mandatory)][string]$ExpectedAccount,
    [Parameter(Mandatory)][ValidateSet('ap-southeast-2a','ap-southeast-2b')][string]$TargetAz,
    [Parameter(Mandatory)][string]$TargetGroupArn,
    [string]$Region = 'ap-southeast-2',
    [string]$Cluster = 'labseat-lab',
    [string]$Asg = 'labseat-lab-app',
    [string[]]$Services = @('labseat-lab-api','labseat-lab-worker','labseat-lab-publisher'),
    [string]$OutputDir = '.local/assessment/c4-preflight'
)

$ErrorActionPreference = 'Stop'
if ($ExpectedAccount -notmatch '^\d{12}$') { throw 'ExpectedAccount must be a 12-digit account ID' }
if ($Region -ne 'ap-southeast-2') { throw 'C4 is restricted to ap-southeast-2' }
if (@($Services).Count -ne 3 -or @($Services | Select-Object -Unique).Count -ne 3) {
    throw 'Exactly three distinct essential ECS services are required'
}
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$privateRoot = [IO.Path]::GetFullPath((Join-Path $workspace '.local\assessment'))
$output = [IO.Path]::GetFullPath((Join-Path (Get-Location).Path $OutputDir))
if (-not $output.StartsWith($privateRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDir must be below workspace .local/assessment and outside Git'
}

function Read-Aws([string[]]$Arguments) {
    $all = @($Arguments) + @('--profile', $Profile, '--region', $Region, '--output', 'json', '--no-cli-pager')
    $raw = & aws @all 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('AWS read failed: ' + ($Arguments[0..1] -join ' ')) }
    return (($raw -join "`n") | ConvertFrom-Json)
}
function Resource([object]$Instance, [string]$Name) {
    $item = @($Instance.remainingResources | Where-Object name -eq $Name | Select-Object -First 1)
    if ($item.Count -eq 0) { return $null }
    if ($null -ne $item[0].integerValue) { return [int]$item[0].integerValue }
    if ($null -ne $item[0].longValue) { return [int]$item[0].longValue }
    return $null
}
function Task-Ip([object]$Task) {
    $ips = @($Task.attachments | ForEach-Object details | Where-Object name -eq 'privateIPv4Address' | ForEach-Object value | Where-Object { $_ })
    if ($ips.Count -ne 1) { return $null }
    return $ips[0]
}

$identity = Read-Aws @('sts','get-caller-identity')
if ($identity.Account -ne $ExpectedAccount) { throw 'AWS account mismatch; no resource reads performed' }
$groupResult = Read-Aws @('autoscaling','describe-auto-scaling-groups','--auto-scaling-group-names',$Asg)
$group = @($groupResult.AutoScalingGroups)[0]
if (-not $group -or $group.AutoScalingGroupName -ne $Asg) { throw 'Expected ASG not found' }
$serviceResult = Read-Aws (@('ecs','describe-services','--cluster',$Cluster,'--services') + $Services)
$foundServices = @($serviceResult.services)
if ($foundServices.Count -ne 3 -or ($serviceResult.failures -and @($serviceResult.failures).Count -gt 0)) { throw 'Essential ECS services not found' }
$providerNames = @($foundServices | ForEach-Object { $_.capacityProviderStrategy } | ForEach-Object capacityProvider | Where-Object { $_ } | Sort-Object -Unique)
$providers = @()
if ($providerNames.Count -eq 1) {
    $providers = @((Read-Aws @('ecs','describe-capacity-providers','--capacity-providers',$providerNames[0])).capacityProviders)
}
$containerArns = @((Read-Aws @('ecs','list-container-instances','--cluster',$Cluster)).containerInstanceArns)
if ($containerArns.Count -eq 0) { throw 'No ECS container instances registered' }
$containerResult = Read-Aws (@('ecs','describe-container-instances','--cluster',$Cluster,'--container-instances') + $containerArns)
$containers = @($containerResult.containerInstances)
$taskArns = @()
foreach ($service in $Services) {
    $taskArns += @((Read-Aws @('ecs','list-tasks','--cluster',$Cluster,'--service-name',$service,'--desired-status','RUNNING')).taskArns)
}
$tasks = @()
if ($taskArns.Count -gt 0) {
    $tasks = @((Read-Aws (@('ecs','describe-tasks','--cluster',$Cluster,'--tasks') + $taskArns)).tasks)
}
$ec2Ids = @($group.Instances | ForEach-Object InstanceId)
if ($ec2Ids.Count -eq 0) { throw 'ASG has no EC2 instances' }
$ec2 = @((Read-Aws (@('ec2','describe-instances','--instance-ids') + $ec2Ids)).Reservations | ForEach-Object Instances)
$instanceTypes = @($ec2 | ForEach-Object InstanceType | Where-Object { $_ } | Sort-Object -Unique)
$typeLimits = @{}
if ($instanceTypes.Count -gt 0) {
    $typeDescriptions = @((Read-Aws (@('ec2','describe-instance-types','--instance-types') + $instanceTypes)).InstanceTypes)
    foreach ($type in $typeDescriptions) { $typeLimits[$type.InstanceType] = [int]$type.NetworkInfo.MaximumNetworkInterfaces }
}
$subnetIds = @($group.VPCZoneIdentifier -split ',' | Where-Object { $_ })
$subnets = @((Read-Aws (@('ec2','describe-subnets','--subnet-ids') + $subnetIds)).Subnets)
$targets = @((Read-Aws @('elbv2','describe-target-health','--target-group-arn',$TargetGroupArn)).TargetHealthDescriptions)
$survivorAz = if ($TargetAz -eq 'ap-southeast-2a') { 'ap-southeast-2b' } else { 'ap-southeast-2a' }
$byArn = @{}; foreach ($item in $containers) { $byArn[$item.containerInstanceArn] = $item }
$byId = @{}; foreach ($item in $ec2) { $byId[$item.InstanceId] = $item }
$targetIds = @($ec2 | Where-Object { $_.Placement.AvailabilityZone -eq $TargetAz } | ForEach-Object InstanceId | Sort-Object)
$survivorIds = @($ec2 | Where-Object { $_.Placement.AvailabilityZone -eq $survivorAz } | ForEach-Object InstanceId | Sort-Object)
$targetTasks = @($tasks | Where-Object { $byArn.ContainsKey($_.containerInstanceArn) -and $byId[$byArn[$_.containerInstanceArn].ec2InstanceId].Placement.AvailabilityZone -eq $TargetAz })
$survivor = @($containers | Where-Object { $byId.ContainsKey($_.ec2InstanceId) -and $byId[$_.ec2InstanceId].Placement.AvailabilityZone -eq $survivorAz })
$survivorSubnets = @($subnets | Where-Object AvailabilityZone -eq $survivorAz)
$survivorSubnetIds = @($survivorSubnets | ForEach-Object SubnetId)
$remaining = @{ cpu = 0; memory = 0; eni = 0 }; $unknown = @()
$slots = @()
foreach ($item in $survivor) {
    $slot = @{ instance_id = $item.ec2InstanceId; cpu = 0; memory = 0; eni = 0; eni_source = $null }
    foreach ($name in @('CPU','MEMORY','ENI')) {
        $value = Resource $item $name
        if ($name -eq 'ENI' -and $null -eq $value) {
            $hostInstance = $byId[$item.ec2InstanceId]
            $trunk = @($item.attributes | Where-Object name -eq 'ecs.awsvpc-trunk-id')
            if ($hostInstance -and $trunk.Count -eq 0 -and $typeLimits.ContainsKey($hostInstance.InstanceType) -and
                $typeLimits[$hostInstance.InstanceType] -gt 0 -and $null -ne $hostInstance.NetworkInterfaces) {
                $value = $typeLimits[$hostInstance.InstanceType] - @($hostInstance.NetworkInterfaces).Count
                $slot.eni_source = 'ec2_native_interface_limit_minus_attached'
            }
        } elseif ($name -eq 'ENI' -and $null -ne $value) {
            $slot.eni_source = 'ecs_remainingResources'
        }
        if ($null -eq $value) { $unknown += "$($item.ec2InstanceId):$name" }
        elseif ($value -lt 0) { $unknown += "$($item.ec2InstanceId):${name}_negative" }
        else {
            $key = $name.ToLower()
            $remaining[$key] += $value
            $slot[$key] = $value
        }
    }
    $slots += $slot
}
$targetTaskCpu = 0; $targetTaskMemory = 0
$requirements = @()
foreach ($task in $targetTasks) {
    if (-not $task.cpu -or -not $task.memory -or [int]$task.cpu -le 0 -or [int]$task.memory -le 0) {
        $unknown += "$($task.taskArn):task_cpu_or_memory"
        continue
    }
    $cpu = [int]$task.cpu; $memory = [int]$task.memory
    $targetTaskCpu += $cpu; $targetTaskMemory += $memory
    $requirements += @{ task_arn = $task.taskArn; cpu = $cpu; memory = $memory; eni = 1 }
}
# A successful first-fit decreasing placement proves a conservative lower bound.
# A failed fit is BLOCKED; this does not claim ECS itself could never place the tasks.
$placement = @()
$initialSlots = @($slots | ForEach-Object { @{ instance_id = $_.instance_id; cpu = $_.cpu; memory = $_.memory; eni = $_.eni; eni_source = $_.eni_source } })
if ($unknown.Count -eq 0) {
    foreach ($need in @($requirements | Sort-Object -Property @{ Expression = 'memory'; Descending = $true }, @{ Expression = 'cpu'; Descending = $true })) {
        $fit = @($slots | Where-Object { $_.cpu -ge $need.cpu -and $_.memory -ge $need.memory -and $_.eni -ge 1 } |
            Sort-Object -Property @{ Expression = 'memory'; Descending = $false }, @{ Expression = 'cpu'; Descending = $false } | Select-Object -First 1)
        if ($fit.Count -eq 0) { break }
        $fit[0].cpu -= $need.cpu; $fit[0].memory -= $need.memory; $fit[0].eni -= 1
        $placement += @{ task_arn = $need.task_arn; instance_id = $fit[0].instance_id }
    }
}
$slotsProven = $unknown.Count -eq 0 -and $placement.Count -eq $targetTasks.Count
$apiTemplate = @($tasks | Where-Object group -eq 'service:labseat-lab-api' | Select-Object -First 1)
$apiOverlapProven = $false
if ($slotsProven -and $apiTemplate.Count -eq 1 -and $apiTemplate[0].cpu -and $apiTemplate[0].memory) {
    $apiCpu = [int]$apiTemplate[0].cpu; $apiMemory = [int]$apiTemplate[0].memory
    $apiOverlapProven = @($slots | Where-Object { $_.cpu -ge $apiCpu -and $_.memory -ge $apiMemory -and $_.eni -ge 1 }).Count -gt 0
}
$targetApi = @($targetTasks | Where-Object group -eq 'service:labseat-lab-api').Count
$survivorApiTasks = @($tasks | Where-Object { $_.group -eq 'service:labseat-lab-api' -and
    $byArn.ContainsKey($_.containerInstanceArn) -and $byId[$byArn[$_.containerInstanceArn].ec2InstanceId].Placement.AvailabilityZone -eq $survivorAz })
$healthyTargetIps = @($targets | Where-Object { $_.TargetHealth.State -eq 'healthy' } | ForEach-Object { $_.Target.Id })
$targetApiHealthy = @($targetTasks | Where-Object group -eq 'service:labseat-lab-api' | Where-Object { (Task-Ip $_) -in $healthyTargetIps }).Count
$survivorApiHealthy = @($survivorApiTasks | Where-Object { (Task-Ip $_) -in $healthyTargetIps }).Count
$targetWorker = @($targetTasks | Where-Object group -eq 'service:labseat-lab-worker').Count
$targetPublisher = @($targetTasks | Where-Object group -eq 'service:labseat-lab-publisher').Count
$readiness = [ordered]@{
    identity_region = 'PASS'; target_has_api = if ($targetApi -gt 0) { 'PASS' } else { 'BLOCKED' }
    target_list = if ($targetIds.Count -gt 0 -and $targetIds.Count -lt $ec2Ids.Count) { 'PASS' } else { 'BLOCKED' }
    asg_instances_healthy = if (@($group.Instances | Where-Object { $_.LifecycleState -ne 'InService' -or $_.HealthStatus -ne 'Healthy' }).Count -eq 0 -and
        @($ec2 | Where-Object { $_.State.Name -ne 'running' }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    ecs_agents_connected = if ($containers.Count -eq $ec2Ids.Count -and
        @($containers | Where-Object { $_.status -ne 'ACTIVE' -or $_.agentConnected -ne $true }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    services_stable = if (@($foundServices | Where-Object { $_.runningCount -ne $_.desiredCount -or $_.pendingCount -ne 0 -or @($_.deployments).Count -ne 1 }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    alb_healthy = if (@($targets | Where-Object { $_.TargetHealth.State -eq 'healthy' }).Count -ge 2) { 'PASS' } else { 'BLOCKED' }
    alb_api_az_coverage = if ($targetApiHealthy -gt 0 -and $survivorApiHealthy -gt 0) { 'PASS' } else { 'BLOCKED' }
    api_target_group = if (@($foundServices | Where-Object serviceName -eq 'labseat-lab-api' | ForEach-Object loadBalancers | Where-Object targetGroupArn -eq $TargetGroupArn).Count -eq 1) { 'PASS' } else { 'BLOCKED' }
    provider_asg_match = if ($providers.Count -eq 1 -and $providers[0].autoScalingGroupProvider.autoScalingGroupArn -eq $group.AutoScalingGroupARN) { 'PASS' } else { 'BLOCKED' }
    all_tasks_in_asg = if (@($tasks | Where-Object { -not $byArn.ContainsKey($_.containerInstanceArn) -or -not $byId.ContainsKey($byArn[$_.containerInstanceArn].ec2InstanceId) }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    survivor_service_subnets = if (@($foundServices | Where-Object { @($_.networkConfiguration.awsvpcConfiguration.subnets | Where-Object { $_ -in $survivorSubnetIds }).Count -eq 0 }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    exact_survivor_slots = if ($slotsProven) { 'PASS' } else { 'BLOCKED' }
    survivor_api_overlap = if ($apiOverlapProven) { 'PASS' } else { 'BLOCKED' }
    survivor_subnet_ips = if ($survivorSubnets.Count -gt 0 -and @($survivorSubnets | Where-Object { $_.AvailableIpAddressCount -lt ($targetTasks.Count + 5) }).Count -eq 0) { 'PASS' } else { 'BLOCKED' }
    asg_limit = if ($group.MaxSize -le 6 -and $group.DesiredCapacity -le 6) { 'PASS' } else { 'BLOCKED' }
    c3_b3_c2_window = 'BLOCKED'; no_concurrent_fault_restore = 'BLOCKED'; rollback_authority = 'BLOCKED'
}
$snapshot = [ordered]@{
    run_id = 'c4-preflight-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    observed_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    account = $identity.Account; region = $Region; cluster = $Cluster; asg_name = $Asg; target_group_arn = $TargetGroupArn
    target_az = $TargetAz; survivor_az = $survivorAz
    baseline = @{ asg = $group; services = $foundServices; capacity_providers = $providers; containers = $containers; ec2 = $ec2; subnets = $subnets; tasks = $tasks; target_health = $targets }
    dry_run = @{ target_instance_ids = $targetIds; survivor_instance_ids = $survivorIds; target_task_arns = @($targetTasks | ForEach-Object taskArn); target_service_tasks = @{ api = $targetApi; worker = $targetWorker; publisher = $targetPublisher }; healthy_api_by_az = @{ target = $targetApiHealthy; survivor = $survivorApiHealthy }; survivor_remaining = $remaining; survivor_slots = $initialSlots; placement_dry_run = $placement; missing_resources = $unknown; target_cpu = $targetTaskCpu; target_memory_mib = $targetTaskMemory }
    gates = $readiness
}
New-Item -ItemType Directory -Path $output -Force | Out-Null
$path = Join-Path $output 'baseline.private.json'
$snapshot | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $path -Encoding utf8
Write-Output "Private C4 baseline: $path"
Write-Output "Target AZ=$TargetAz instances=$($targetIds.Count) API tasks=$targetApi; survivor=$survivorAz instances=$($survivorIds.Count)"
foreach ($key in $readiness.Keys) { Write-Output "$key=$($readiness[$key])" }
Write-Output 'No AWS mutation was performed. Injection remains BLOCKED until all gates have fresh evidence.'
