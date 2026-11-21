param(
    [Parameter(Mandatory=$true)][string]$OutputCsv,
    [ValidateRange(1,100000)][int]$Samples = 1,
    [ValidateRange(15,30)][int]$IntervalSeconds = 30
)

$ErrorActionPreference = 'Stop'
$outputPath = [System.IO.Path]::GetFullPath($OutputCsv)
$parent = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$rows = [System.Collections.Generic.List[object]]::new()
for ($i = 0; $i -lt $Samples; $i++) {
    $stamp = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    try {
        $counter = Get-Counter -Counter '\Processor(_Total)\% Processor Time', '\Memory\Available MBytes', '\Network Interface(*)\Bytes Total/sec' -ErrorAction Stop
        $cpu = ($counter.CounterSamples | Where-Object Path -Like '*processor(_total)*' | Select-Object -First 1).CookedValue
        $memory = ($counter.CounterSamples | Where-Object Path -Like '*memory*available mbytes*' | Select-Object -First 1).CookedValue
        $network = ($counter.CounterSamples | Where-Object Path -Like '*network interface*' | Measure-Object -Property CookedValue -Sum).Sum
        $rows.Add([pscustomobject]@{sample_at=$stamp;cpu_percent=[math]::Round($cpu,2);available_memory_mb=[math]::Round($memory,2);network_bytes_per_sec=[math]::Round($network,2);status='OBSERVED'})
    } catch {
        $rows.Add([pscustomobject]@{sample_at=$stamp;cpu_percent='';available_memory_mb='';network_bytes_per_sec='';status='COUNTER_UNAVAILABLE'})
    }
    $rows | Export-Csv -LiteralPath $outputPath -NoTypeInformation -Encoding utf8
    if ($i + 1 -lt $Samples) { Start-Sleep -Seconds $IntervalSeconds }
}
Write-Output "Runner CSV: $outputPath"
