param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9-]{2,23}$')][string]$Batch,
    [string]$Aws = 'aws',
    [string]$Profile = 'labseat',
    [string]$Region = 'ap-southeast-2',
    [int]$TunnelPort = 15432,
    [string]$Image = 'labseat-assessment-b1b2:local',
    [string]$BaseUrl = 'https://labseat.id.vn',
    [ValidateRange(3600, 28500)][int]$MinimumValidSeconds = 14400,
    [switch]$Execute
)
$ErrorActionPreference = 'Stop'
if (-not $Execute) {
    Write-Output "Plan only: create handoff for $Batch over existing tunnel port $TunnelPort"
    return
}
$root = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$privateDir = Join-Path $root '.local'
New-Item -ItemType Directory -Path $privateDir -Force | Out-Null
$source = Join-Path $root 'app'
$scripts = Join-Path $root 'scripts'
$url = & $Aws ssm get-parameter --profile $Profile --region $Region --name /labseat/lab/DATABASE_URL --with-decryption --query Parameter.Value --output text --no-cli-pager
if ($LASTEXITCODE -or -not $url) { throw 'Could not read the RDS parameter' }
$command = @'
import json, os, socket, sys
from pathlib import Path
from sqlalchemy.engine import make_url
url = make_url(sys.stdin.readline().strip()).set(port=int(sys.argv[2]))
url = url.update_query_dict({
    "hostaddr": socket.gethostbyname("host.docker.internal"),
    "sslrootcert": "/srv/labseat/app/infrastructure/database/rds-global-bundle.crt",
    "sslmode": "verify-full",
})
os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
from app.assessment_seed import main, password, save_private
batch = sys.argv[1]
sys.argv = ["assessment_seed", "sessions", "--batch", batch, "--execute",
            "--minimum-valid-seconds", sys.argv[3]]
main()
directory = Path(".local/assessment") / batch
master_path = directory / "seed-master.txt"
if master_path.exists():
    master = master_path.read_text().strip()
    manifest = json.loads((directory / "manifest.json").read_text())
    save_private(directory / "accounts.json", [
        {"username": user["username"], "role": user["role"],
         "password": password(master, user["username"])}
        for user in manifest["users"]
    ])
'@
$start = @('run', '-i', '--rm', '-w', '/workspace', '-e', 'PYTHONPATH=/srv/labseat', '-e', 'APP_ENV=production',
    '--mount', "type=bind,source=$source,target=/srv/labseat/app,readonly",
    '--mount', "type=bind,source=$privateDir,target=/workspace/.local",
    $Image, 'python', '-c', $command, $Batch, $TunnelPort, $MinimumValidSeconds)
try {
    $url | docker @start
    if ($LASTEXITCODE) { throw 'Could not create B2 login sessions' }
} finally {
    Remove-Variable url -ErrorAction SilentlyContinue
}
$smoke = @('run', '--rm', '--mount', "type=bind,source=$scripts,target=/srv/labseat/scripts,readonly",
    '--mount', "type=bind,source=$privateDir,target=/handoff,readonly",
    $Image, 'python', '/srv/labseat/scripts/assessment/data/smoke_sessions.py',
    "/handoff/assessment/$Batch", '--base-url', $BaseUrl,
    '--minimum-valid-seconds', $MinimumValidSeconds)
docker @smoke
if ($LASTEXITCODE) { throw 'B2 HTTP smoke failed; do not distribute the handoff yet' }
