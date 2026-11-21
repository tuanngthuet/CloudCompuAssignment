param(
    [string]$BaseUrl = 'https://labseat.id.vn',
    [ValidateRange(15,30)][int]$IntervalSeconds = 15,
    [ValidateRange(1,960)][int]$Samples = 240,
    [Parameter(Mandatory)][string]$OutputCsv
)

$ErrorActionPreference = 'Stop'
if ($BaseUrl -notmatch '^https://[^/?#]+/?$') { throw 'BaseUrl must be an HTTPS origin without query/path' }
$base = $BaseUrl.TrimEnd('/')
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$privateRoot = [IO.Path]::GetFullPath((Join-Path $workspace '.local\assessment'))
$output = [IO.Path]::GetFullPath((Join-Path (Get-Location).Path $OutputCsv))
if (-not $output.StartsWith($privateRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputCsv must be below workspace .local/assessment and outside Git'
}
New-Item -ItemType Directory -Path (Split-Path -Parent $output) -Force | Out-Null
if (Test-Path -LiteralPath $output) { throw 'OutputCsv already exists; use a new file for each run' }

for ($i = 0; $i -lt $Samples; $i++) {
    $started = [DateTimeOffset]::UtcNow
    foreach ($route in @('/healthz','/events')) {
        $status = 'ERROR'; $seconds = $null
        try {
            $result = & curl.exe --silent --show-error --max-time 10 --output NUL `
                --write-out '%{http_code},%{time_total}' ($base + $route) 2>$null
            if ($LASTEXITCODE -eq 0 -and $result -match '^(\d{3}),([0-9.]+)$') {
                $status = $Matches[1]; $seconds = [double]::Parse($Matches[2], [Globalization.CultureInfo]::InvariantCulture)
            }
        } catch { }
        $row = [pscustomobject]@{
            sample_at_utc = [DateTimeOffset]::UtcNow.ToString('o'); route = $route
            status = $status; duration_ms = if ($null -eq $seconds) { '' } else { [math]::Round($seconds * 1000, 2) }
        }
        $row | Export-Csv -LiteralPath $output -NoTypeInformation -Encoding utf8 -Append
    }
    $remaining = $IntervalSeconds - ([DateTimeOffset]::UtcNow - $started).TotalSeconds
    if ($i + 1 -lt $Samples -and $remaining -gt 0) { Start-Sleep -Milliseconds ([int]($remaining * 1000)) }
}
Write-Output "C4 HTTP probe CSV: $output"
