$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Get-Command terraform -ErrorAction Stop | Out-Null
function Invoke-Terraform {
    param([string[]]$TfArgs)
    & terraform @TfArgs
    if ($LASTEXITCODE -ne 0) { throw "Terraform failed (exit $LASTEXITCODE): $TfArgs" }
}
Invoke-Terraform -TfArgs @("-chdir=$root", "fmt", "-check", "-recursive")
$dirs = @("infra/modules/network", "infra/bootstrap/state", "infra/bootstrap/network-stack")
foreach ($dir in $dirs) {
    # Isolated metadata: does not overwrite an initialized deployment backend.
    $oldData = $env:TF_DATA_DIR
    $checkData = Join-Path ([IO.Path]::GetTempPath()) ("tv1-check-" + [guid]::NewGuid().ToString())
    $env:TF_DATA_DIR = $checkData
    try {
        $path = Join-Path $root $dir
        Invoke-Terraform -TfArgs @("-chdir=$path", "init", "-backend=false", "-input=false", "-lockfile=readonly")
        Invoke-Terraform -TfArgs @("-chdir=$path", "validate", "-no-color")
        if ($dir -ne "infra/bootstrap/network-stack") {
            Invoke-Terraform -TfArgs @("-chdir=$path", "test", "-no-color")
        }
    } finally {
        if (Test-Path $checkData) { Remove-Item -LiteralPath $checkData -Recurse -Force }
        $env:TF_DATA_DIR = $oldData
    }
}
Write-Host "PASS: fmt, validate and mocked contract tests. No AWS deployment performed."
