# Rebuild metadata only from tracked, existing files; never recursively scan secrets.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $root
try {
    $names = & git -c core.quotepath=false ls-files
    if ($LASTEXITCODE -ne 0) { throw 'Run this script inside the TV1 Git repository.' }
    $hashes = [ordered]@{}
    foreach ($name in ($names | Sort-Object)) {
        if ($name -eq 'handoff/files.sha256.json') { continue }
        if ($name -match '(^|/)(\.git|\.vs|\.terraform|\.aws|local-evidence)/' -or
            $name -match '\.(tfstate|tfplan)(\.|$)' -or
            $name -match '\.(pem|ppk)$' -or
            $name -match '\.tfvars(\.json)?$' -or
            $name -match '(^|/)(backend\.hcl|\.env(\..*)?)$') {
            throw "Potential private/generated file is tracked: $name. Remove it from the Git index before continuing."
        }
        if (-not (Test-Path -LiteralPath $name -PathType Leaf)) { throw "Tracked file missing: $name" }
        $hashes[$name] = (Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $json = ConvertTo-Json -InputObject $hashes -Depth 3
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $root 'handoff/files.sha256.json'), $json + "`n", $utf8)
    Write-Host 'Updated handoff/files.sha256.json for the current tracked working files.'
} finally {
    Pop-Location
}
