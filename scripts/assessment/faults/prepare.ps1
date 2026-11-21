param(
    [Parameter(Mandatory)][string]$Profile,
    [Parameter(Mandatory)][string]$ExpectedAccount,
    [Parameter(Mandatory)][string]$BaselinePath,
    [Parameter(Mandatory)][string]$AttestationPath,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$baselineFull = [IO.Path]::GetFullPath($BaselinePath)
if (-not (Test-Path -LiteralPath $baselineFull -PathType Leaf)) { throw 'Private baseline missing' }
$baseline = Get-Content -LiteralPath $baselineFull -Raw -Encoding utf8 | ConvertFrom-Json
$attest = Get-Content -LiteralPath ([IO.Path]::GetFullPath($AttestationPath)) -Raw -Encoding utf8 | ConvertFrom-Json
if ($baseline.account -ne $ExpectedAccount -or $baseline.region -ne 'ap-southeast-2') { throw 'Baseline identity mismatch' }
foreach ($gate in @('target_has_api','target_list','asg_instances_healthy','ecs_agents_connected','services_stable','alb_healthy','alb_api_az_coverage','api_target_group',
                   'provider_asg_match','all_tasks_in_asg','survivor_service_subnets',
                   'exact_survivor_slots','survivor_api_overlap','survivor_subnet_ips','asg_limit')) {
    if ($baseline.gates.$gate -ne 'PASS') { throw "Preflight gate $gate is not PASS" }
}
foreach ($gate in @('c3_finished_and_stable','b3_probe_pass','c2_email_disabled_verified',
                   'clock_synchronized','no_concurrent_fault_restore','rollback_authority_verified','window_approved')) {
    if ($attest.$gate -ne $true -or -not $attest.evidence.$gate) { throw "Attestation/evidence missing: $gate" }
}
if (([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($baseline.observed_at_utc)).TotalMinutes -gt 10) {
    throw 'Baseline older than 10 minutes; rerun preflight'
}
function Aws-Json([string[]]$Arguments) {
    $raw = & aws @Arguments --profile $Profile --region ap-southeast-2 --output json --no-cli-pager 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('AWS call failed: ' + ($Arguments[0..1] -join ' ')) }
    if (-not $raw) { return $null }
    return (($raw -join "`n") | ConvertFrom-Json)
}
function Same-Values([object[]]$Left, [object[]]$Right) {
    return ((@($Left | Sort-Object) -join ',') -ceq (@($Right | Sort-Object) -join ','))
}
function Verify-Target([string]$Phase) {
    $dir = Join-Path (Split-Path -Parent $baselineFull) ('verify-' + $Phase + '-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
    & (Join-Path $PSScriptRoot 'preflight.ps1') -Profile $Profile -ExpectedAccount $ExpectedAccount `
        -TargetAz $baseline.target_az -TargetGroupArn $baseline.target_group_arn `
        -Cluster $baseline.cluster -Asg $baseline.asg_name `
        -Services @($baseline.baseline.services | ForEach-Object serviceName) -OutputDir $dir | Out-Null
    $current = Get-Content -LiteralPath (Join-Path $dir 'baseline.private.json') -Raw -Encoding utf8 | ConvertFrom-Json
    if (-not (Same-Values @($baseline.dry_run.target_instance_ids) @($current.dry_run.target_instance_ids)) -or
        -not (Same-Values @($baseline.dry_run.target_task_arns) @($current.dry_run.target_task_arns)) -or
        $current.gates.asg_instances_healthy -ne 'PASS' -or $current.gates.ecs_agents_connected -ne 'PASS' -or
        $current.gates.services_stable -ne 'PASS' -or $current.gates.alb_healthy -ne 'PASS' -or
        $current.gates.alb_api_az_coverage -ne 'PASS') {
        throw "Target EC2/task or health changed before inject at $Phase; rollback immediately"
    }
    return $current
}
$identity = Aws-Json @('sts','get-caller-identity')
if ($identity.Account -ne $ExpectedAccount) { throw 'Live AWS account mismatch' }
$survivorSubnets = @($baseline.baseline.subnets | Where-Object AvailabilityZone -eq $baseline.survivor_az | ForEach-Object SubnetId | Sort-Object)
if ($survivorSubnets.Count -lt 1) { throw 'No survivor app subnet in baseline' }
$expression = "attribute:ecs.availability-zone == $($baseline.survivor_az)"
$serviceInputs = @()
foreach ($service in @($baseline.baseline.services)) {
    $old = @($service.placementConstraints | Where-Object { $null -ne $_ })
    if ($old.Count -ge 10 -or @($old | Where-Object type -eq 'memberOf').Count -gt 0) {
        throw "Existing placement constraints need manual review: $($service.serviceName)"
    }
    $constraint = @{ type = 'memberOf'; expression = $expression }
    $new = @($old) + @($constraint)
    $serviceInputs += @{ cluster = $baseline.cluster; service = $service.serviceName; placementConstraints = $new }
}
Write-Output "Prepare plan: suspend AZRebalance/AlarmNotification if active; constrain $($serviceInputs.Count) services to $($baseline.survivor_az); restrict ASG to $($survivorSubnets.Count) survivor subnet(s)."
Write-Output 'Target task/EC2 IDs must remain unchanged after every step. Existing task definition, network config and desired counts are not edited.'
if (-not $Execute) { Write-Output 'Dry-run only; no AWS mutation. Re-run with -Execute inside approved window.'; exit 0 }

$recordDir = Split-Path -Parent $baselineFull
$steps = [System.Collections.Generic.List[object]]::new()
try {
    $null = Verify-Target 'before'
    $oldSuspended = @($baseline.baseline.asg.SuspendedProcesses | ForEach-Object ProcessName)
    $toSuspend = @(@('AZRebalance','AlarmNotification') | Where-Object { $_ -notin $oldSuspended })
    if ($toSuspend.Count -gt 0) {
        $null = Aws-Json (@('autoscaling','suspend-processes','--auto-scaling-group-name',$baseline.asg_name,'--scaling-processes') + $toSuspend)
        $steps.Add(@{ at_utc = [DateTimeOffset]::UtcNow.ToString('o'); step = 'suspend_processes'; names = $toSuspend })
    }
    $null = Verify-Target 'suspended'
    foreach ($serviceInput in $serviceInputs) {
        $path = Join-Path $recordDir ('prepare-' + $serviceInput.service + '.private.json')
        [IO.File]::WriteAllText($path, ($serviceInput | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding -ArgumentList $false))
        $null = Aws-Json @('ecs','update-service','--cli-input-json',('file://' + $path.Replace('\','/')))
        $steps.Add(@{ at_utc = [DateTimeOffset]::UtcNow.ToString('o'); step = 'placement_constraint'; service = $serviceInput.service })
        $null = Verify-Target ('service-' + $serviceInput.service)
    }
    $null = Aws-Json @('autoscaling','update-auto-scaling-group','--auto-scaling-group-name',$baseline.asg_name,
                       '--vpc-zone-identifier',($survivorSubnets -join ','))
    $steps.Add(@{ at_utc = [DateTimeOffset]::UtcNow.ToString('o'); step = 'restrict_asg_subnets'; subnet_count = $survivorSubnets.Count })
    $prepared = Verify-Target 'prepared'
    if (-not (Same-Values $survivorSubnets @($prepared.baseline.subnets | ForEach-Object SubnetId))) {
        throw 'ASG subnet restriction was not observed'
    }
    if (@($prepared.baseline.asg.SuspendedProcesses | ForEach-Object ProcessName) -notcontains 'AZRebalance') {
        throw 'AZRebalance suspension was not observed'
    }
    foreach ($service in @($prepared.baseline.services)) {
        if (@($service.placementConstraints | Where-Object { $_.type -eq 'memberOf' -and $_.expression -eq $expression }).Count -ne 1) {
            throw "Survivor placement constraint was not observed: $($service.serviceName)"
        }
    }
    $preparedPath = Join-Path $recordDir 'prepared.private.json'
    $prepared | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $preparedPath -Encoding utf8
    Write-Output "Prepared snapshot: $preparedPath"
} catch {
    Write-Warning 'Prepare failed or moved target before inject. Attempting exact baseline rollback.'
    try { & (Join-Path $PSScriptRoot 'rollback.ps1') -Profile $Profile -ExpectedAccount $ExpectedAccount -BaselinePath $baselineFull -Execute }
    catch { Write-Warning 'Automatic rollback request failed; operator must use baseline and incident runbook immediately.' }
    throw
} finally {
    $recordPath = Join-Path $recordDir ('prepare-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.private.json')
    @{ baseline = $baselineFull; steps = @($steps.ToArray()); note = 'Verify prepared gates and task IDs before inject' } |
        ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $recordPath -Encoding utf8
    Write-Output "Private prepare record: $recordPath"
}
