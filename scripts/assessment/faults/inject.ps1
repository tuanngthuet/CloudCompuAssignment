param(
    [Parameter(Mandatory)][string]$Profile,
    [Parameter(Mandatory)][string]$ExpectedAccount,
    [Parameter(Mandatory)][string]$BaselinePath,
    [Parameter(Mandatory)][string]$PreparedPath,
    [Parameter(Mandatory)][string]$AttestationPath,
    [string]$ConfirmInstanceIds = '',
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
function Read-Private([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw "Private input missing: $full" }
    return (Get-Content -LiteralPath $full -Raw -Encoding utf8 | ConvertFrom-Json)
}
function Same-Ids([object[]]$Left, [object[]]$Right) {
    return ((@($Left | Sort-Object) -join ',') -ceq (@($Right | Sort-Object) -join ','))
}
function Aws-Json([string[]]$Arguments) {
    $raw = & aws @Arguments --profile $Profile --region ap-southeast-2 --output json --no-cli-pager 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('AWS call failed: ' + ($Arguments[0..1] -join ' ')) }
    return (($raw -join "`n") | ConvertFrom-Json)
}

$baseline = Read-Private $BaselinePath
$prepared = Read-Private $PreparedPath
$attest = Read-Private $AttestationPath
if ($baseline.account -ne $ExpectedAccount -or $prepared.account -ne $ExpectedAccount -or
    $baseline.region -ne 'ap-southeast-2' -or $prepared.region -ne 'ap-southeast-2' -or
    $baseline.asg_name -ne $prepared.asg_name -or $baseline.target_az -ne $prepared.target_az -or
    $baseline.target_group_arn -ne $prepared.target_group_arn) { throw 'Baseline/prepared identity mismatch' }
if (-not (Same-Ids @($baseline.dry_run.target_instance_ids) @($prepared.dry_run.target_instance_ids)) -or
    -not (Same-Ids @($baseline.dry_run.target_task_arns) @($prepared.dry_run.target_task_arns))) {
    throw 'Target EC2 or task list changed during preparation; rollback, do not inject'
}
$targetIds = @($baseline.dry_run.target_instance_ids | Sort-Object)
if ($targetIds.Count -lt 1 -or $targetIds.Count -ge @($baseline.baseline.ec2).Count -or
    @($targetIds | Where-Object { $_ -notmatch '^i-[0-9a-f]{8,17}$' }).Count -gt 0) {
    throw 'Target list is empty, malformed or covers the whole ASG'
}
foreach ($gate in @('target_has_api','target_list','asg_instances_healthy','ecs_agents_connected','services_stable','alb_healthy','alb_api_az_coverage','api_target_group',
                   'provider_asg_match','all_tasks_in_asg','survivor_service_subnets',
                   'exact_survivor_slots','survivor_api_overlap','survivor_subnet_ips','asg_limit')) {
    if ($prepared.gates.$gate -ne 'PASS') { throw "Prepared gate $gate is not PASS" }
}
foreach ($gate in @('c3_finished_and_stable','b3_probe_pass','c2_email_disabled_verified',
                   'clock_synchronized','no_concurrent_fault_restore','rollback_authority_verified','window_approved')) {
    if ($attest.$gate -ne $true -or -not $attest.evidence.$gate) { throw "Attestation/evidence missing: $gate" }
}
$preparedAt = [DateTimeOffset]::Parse($prepared.observed_at_utc)
if (([DateTimeOffset]::UtcNow - $preparedAt).TotalMinutes -gt 10) { throw 'Prepared snapshot older than 10 minutes' }
$survivorSubnets = @($baseline.baseline.subnets | Where-Object AvailabilityZone -eq $baseline.survivor_az | ForEach-Object SubnetId | Sort-Object)
$preparedSubnets = @($prepared.baseline.subnets | ForEach-Object SubnetId | Sort-Object)
if ($survivorSubnets.Count -lt 1 -or -not (Same-Ids $survivorSubnets $preparedSubnets)) {
    throw 'Prepared ASG is not restricted to survivor app subnet(s)'
}
$suspended = @($prepared.baseline.asg.SuspendedProcesses | ForEach-Object ProcessName)
if ($suspended -notcontains 'AZRebalance') { throw 'AZRebalance is not suspended' }
$expression = "attribute:ecs.availability-zone == $($baseline.survivor_az)"
foreach ($service in @($prepared.baseline.services)) {
    if (@($service.placementConstraints | Where-Object { $_.type -eq 'memberOf' -and $_.expression -eq $expression }).Count -ne 1) {
        throw "Survivor placement constraint missing: $($service.serviceName)"
    }
}
$confirmed = @($ConfirmInstanceIds -split ',' | ForEach-Object Trim | Where-Object { $_ })
if (-not (Same-Ids $targetIds $confirmed)) { throw 'ConfirmInstanceIds must exactly match locked target list' }
$identity = Aws-Json @('sts','get-caller-identity')
if ($identity.Account -ne $ExpectedAccount) { throw 'Live AWS account mismatch' }
$liveDir = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($PreparedPath))) ('live-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
& (Join-Path $PSScriptRoot 'preflight.ps1') -Profile $Profile -ExpectedAccount $ExpectedAccount `
    -TargetAz $baseline.target_az -TargetGroupArn $baseline.target_group_arn `
    -Cluster $baseline.cluster -Asg $baseline.asg_name `
    -Services @($baseline.baseline.services | ForEach-Object serviceName) -OutputDir $liveDir | Out-Null
$live = Read-Private (Join-Path $liveDir 'baseline.private.json')
if (-not (Same-Ids $targetIds @($live.dry_run.target_instance_ids)) -or
    -not (Same-Ids @($baseline.dry_run.target_task_arns) @($live.dry_run.target_task_arns)) -or
    -not (Same-Ids $survivorSubnets @($live.baseline.subnets | ForEach-Object SubnetId))) {
    throw 'Live target/placement changed; no EC2 stop performed'
}
if (@($live.baseline.asg.SuspendedProcesses | ForEach-Object ProcessName) -notcontains 'AZRebalance') {
    throw 'Live AZRebalance suspension missing'
}
foreach ($service in @($live.baseline.services)) {
    if (@($service.placementConstraints | Where-Object { $_.type -eq 'memberOf' -and $_.expression -eq $expression }).Count -ne 1) {
        throw "Live placement constraint changed: $($service.serviceName)"
    }
}
if (@($live.baseline.ec2 | Where-Object { $_.InstanceId -in $targetIds -and $_.State.Name -ne 'running' }).Count -gt 0) {
    throw 'A target EC2 is no longer running before injection'
}
foreach ($gate in @('asg_instances_healthy','ecs_agents_connected','services_stable','alb_healthy','alb_api_az_coverage','api_target_group','provider_asg_match',
                   'all_tasks_in_asg','survivor_service_subnets','exact_survivor_slots','survivor_api_overlap','survivor_subnet_ips')) {
    if ($live.gates.$gate -ne 'PASS') { throw "Live gate $gate is not PASS" }
}
Write-Output "Dry-run target AZ=$($baseline.target_az), EC2 count=$($targetIds.Count); live checks PASS."
Write-Output ('Locked EC2 IDs: ' + ($targetIds -join ','))
if (-not $Execute) { Write-Output 'No instance stopped. Re-run with -Execute only inside approved C4 window.'; exit 0 }
$incidentAt = [DateTimeOffset]::UtcNow.ToString('o')
$response = Aws-Json (@('ec2','stop-instances','--instance-ids') + $targetIds)
$record = @{ incident_at_utc = $incidentAt; target_az = $baseline.target_az; target_instance_ids = $targetIds; stop_response = $response }
$recordPath = Join-Path $liveDir 'inject.private.json'
$record | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $recordPath -Encoding utf8
Write-Output "EC2 stop request sent at $incidentAt; private response: $recordPath"
