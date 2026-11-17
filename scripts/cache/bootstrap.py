"""Fetch cache bootstrap secrets at boot; never print AWS responses or secret errors."""
import json
import os
from pathlib import Path
import subprocess
import sys


def configure():
    version = subprocess.check_output(["/usr/local/bin/redis-server", "--version"], text=True)
    if f"v={os.environ['REDIS_ENGINE_VERSION']} " not in version:
        raise ValueError("Engine version mismatch")
    prefix = os.environ["PARAMETER_PREFIX"]
    keys = ("CA_CERT", "SERVER_CERT", "SERVER_KEY", "ACL_FILE", "MONITOR_PASSWORD")
    result = subprocess.run(["aws", "ssm", "get-parameters", "--region", os.environ["AWS_REGION"],
        "--with-decryption", "--output", "json", "--no-cli-pager", "--names",
        *[prefix + key for key in keys]], capture_output=True, check=True, timeout=30)
    values = {v["Name"].removeprefix(prefix): v for v in json.loads(result.stdout)["Parameters"]}
    if any(not values.get(key, {}).get("Value") for key in keys):
        raise ValueError("Missing cache parameter")
    if any(values[key]["Type"] != "SecureString" for key in ("SERVER_KEY", "ACL_FILE", "MONITOR_PASSWORD")):
        raise ValueError("Cache secrets must use SecureString")
    folder = Path("/run/labseat-cache")
    for key, name in [("CA_CERT", "ca.pem"), ("SERVER_CERT", "server.pem"),
                      ("SERVER_KEY", "server.key"), ("ACL_FILE", "users.acl"),
                      ("MONITOR_PASSWORD", "monitor-password")]:
        target = folder / name
        target.write_text(values[key]["Value"])
        target.chmod(0o600)
    # run_id changes on restart: the app's Lua script rejects any readiness from old AOF.
    (folder / "redis.conf").write_text('''bind 0.0.0.0
protected-mode yes
port 0
tls-port 6379
tls-cert-file /run/labseat-cache/server.pem
tls-key-file /run/labseat-cache/server.key
tls-ca-cert-file /run/labseat-cache/ca.pem
tls-auth-clients no
aclfile /run/labseat-cache/users.acl
unixsocket /run/labseat-cache/redis.sock
unixsocketperm 700
dir /var/lib/labseat-redis
appendonly yes
appendfsync everysec
maxmemory 256mb
maxmemory-policy noeviction
save ""
daemonize no
logfile ""
''')


if __name__ == "__main__":
    try:
        configure()
    except Exception:
        print("Cache bootstrap failed; check parameter names, permissions, certificates and engine pin.", file=sys.stderr)
        sys.exit(1)
