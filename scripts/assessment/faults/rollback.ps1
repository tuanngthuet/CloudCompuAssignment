param(
    [Parameter(Mandatory)][string]$Profile,
    [Parameter(Mandatory)][string]$ExpectedAccount,
    [Parameter(Mandatory)][string]$BaselinePath,
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$baselineFull = [IO.Path]::GetFullPath($BaselinePath)
if (-not (Test-Path -LiteralPath $baselineFull -PathType Leaf)) { throw 'Private baseline file missing' }
$baseline = Get-Content -LiteralPath $baselineFull -Raw -Encoding utf8 | ConvertFrom-Json
if ($baseline.account -ne $ExpectedAccount -or $baseline.region -ne 'ap-southeast-2') { throw 'Baseline account/region mismatch' }
function Aws-Json([string[]]$Arguments) {
    $raw = & aws @Arguments --profile $Profile --region ap-southeast-2 --output json --no-cli-pager 2>&1
    if ($LASTEXITCODE -ne 0) { throw ('AWS call failed: ' + ($Arguments[0..1] -join ' ')) }
    if (-not $raw) { return $null }
    return (($raw -join "`n") | ConvertFrom-Json)
}
function Same-Values([object[]]$Left, [object[]]$Right) {
    return ((@($Left | Sort-Object) -join ',') -ceq (@($Right | Sort-Object) -join ','))
}
$identity = Aws-Json @('sts','get-caller-identity')
if ($identity.Account -ne $ExpectedAccount) { throw 'Live AWS account mismatch' }
$group = @((Aws-Json @('autoscaling','describe-auto-scaling-groups','--auto-scaling-group-names',$baseline.asg_name)).AutoScalingGroups)[0]
if (-not $group -or $group.AutoScalingGroupName -ne $baseline.asg_name) { throw 'ASG missing or changed' }
$originalSubnets = @($baseline.baseline.subnets | ForEach-Object SubnetId | Sort-Object)
$currentSubnets = @($group.VPCZoneIdentifier -split ',' | Where-Object { $_ } | Sort-Object)
if ($originalSubnets.Count -lt 2 -or $currentSubnets.Count -lt 1) { throw 'Unexpected subnet baseline/current state' }
$originalProcesses = @($baseline.baseline.asg.SuspendedProcesses | ForEach-Object ProcessName)
$currentProcesses = @($group.SuspendedProcesses | ForEach-Object ProcessName)
$toResume = @(@('AZRebalance','AlarmNotification') | Where-Object { $_ -notin $originalProcesses -and $_ -in $currentProcesses })
$services = @((Aws-Json (@('ecs','describe-services','--cluster',$baseline.cluster,'--services') + @($baseline.baseline.services | ForEach-Object serviceName))).services)
if ($services.Count -ne @($baseline.baseline.services).Count) { throw 'Essential ECS service missing' }
if (@($currentSubnets | Where-Object { $_ -notin $originalSubnets }).Count -gt 0) {
    throw 'ASG subnets include IDs outside the saved baseline; manual drift review required'
}
$survivorExpression = "attribute:ecs.availability-zone == $($baseline.survivor_az)"
foreach ($original in @($baseline.baseline.services)) {
    $current = @($services | Where-Object serviceName -eq $original.serviceName)[0]
    if (-not $current) { throw "Service missing: $($original.serviceName)" }
    $old = @($original.placementConstraints | Where-Object { $null -ne $_ })
    $actual = @($current.placementConstraints | Where-Object { $null -ne $_ })
    $expectedPrepared = @($old) + @(@{ type = 'memberOf'; expression = $survivorExpression })
    $actualText = @($actual | ForEach-Object { "$($_.type):$($_.expression)" } | Sort-Object) -join ','
    $oldText = @($old | ForEach-Object { "$($_.type):$($_.expression)" } | Sort-Object) -join ','
    $preparedText = @($expectedPrepared | ForEach-Object { "$($_.type):$($_.expression)" } | Sort-Object) -join ','
    if ($actualText -ne $oldText -and $actualText -ne $preparedText) {
        throw "Service placement constraints drifted: $($original.serviceName)"
    }
}
$recordDir = Split-Path -Parent $baselineFull
Write-Output "Restore ASG=$($baseline.asg_name), subnets=$($originalSubnets.Count), services=$($services.Count), resume=$($toResume -join ',')"
if (-not $Execute) { Write-Output 'Dry-run only; no AWS mutation. Re-run with -Execute during C4 rollback.'; exit 0 }

$steps = [System.Collections.Generic.List[object]]::new()
try {
    if (-not (Same-Values $currentSubnets $originalSubnets)) {
        $null = Aws-Json @('autoscaling','update-auto-scaling-group','--auto-scaling-group-name',$baseline.asg_name,
                           '--vpc-zone-identifier',($originalSubnets -join ','))
        $steps.Add(@{ at_utc = [DateTimeOffset]::UtcNow.ToString('o'); step = 'restore_asg_subnets'; status = 'REQUESTED' })
    }
    foreach ($original in @($baseline.baseline.services)) {
        $current = @($services | Where-Object serviceName -eq $original.serviceName)[0]
        if (-not $current) { throw "Service missing: $($original.serviceName)" }
        $originalConstraints = @($original.placementConstraints | Where-Object { $null -ne $_ })
        $currentConstraints = @($current.placementConstraints | Where-Object { $null -ne $_ })
        if (($originalConstraints | ConvertTo-Json -Compress) -ne ($currentConstraints | ConvertTo-Json -Compress)) {
            $inputPath = Join-Path $recordDir ('restore-' + $original.serviceName + '.private.json')
            $payload = @{ cluster = $baseline.cluster; service = $original.serviceName; placementConstraints = $originalConstraints } | ConvertTo-Json -Depth 20
            [IO.File]::WriteAllText($inputPath, $payload, (New-Object System.Text.UTF8Encoding -ArgumentList $false))
            $null = Aws-Json @('ecs','update-service','--cli-input-json',('file://' + $inputPath.Replace('\','/')))
            $steps.Add(@{ at_utc = [DateTimeOffset]::UtcNow.ToString('o'); step = 'restore_service_constraints'; service = $original.serviceName; status = 'REQUESTED' })
        }
    }
    if ($toResume.Count -gt 0) {
        $null = Aws-Json (@('autoscaling','resume-processes','--auto-scaling-group-name',$baseline.asg_name,'--scaling-processes') + $toResume)
        $steps.Add(@{ at_utc = [DateTimeOffset]::UtcNow.ToString('o'); step = 'resume_only_new_processes'; status = 'REQUESTED' })
    }
} finally {
    $recordPath = Join-Path $recordDir ('rollback-' + [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.private.json')
    @{ baseline = $baselineFull; steps = @($steps.ToArray()); note = 'Requests only; verify two-AZ baseline and B3 probes before PASS' } |
        ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $recordPath -Encoding utf8
    Write-Output "Private rollback record: $recordPath"
}
Write-Output 'Rollback requests sent. Verify ECS/ASG/ALB/B3/invariants and two-AZ distribution; do not infer PASS.'
