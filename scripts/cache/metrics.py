"""Publish non-secret Redis INFO metrics using the monitor-only ACL over a Unix socket."""
import json
import os
from pathlib import Path
import subprocess
import sys


def collect():
    env = {**os.environ, "REDISCLI_AUTH": Path("/run/labseat-cache/monitor-password").read_text()}
    info = subprocess.run(["/usr/local/bin/redis-cli", "-s", "/run/labseat-cache/redis.sock",
        "--user", "monitor", "--no-auth-warning", "INFO"], env=env, capture_output=True,
        text=True, check=True, timeout=5).stdout
    values = dict(line.split(":", 1) for line in info.splitlines() if ":" in line and not line.startswith("#"))
    import urllib.request
    # IMDSv2 only; metadata is not a secret and is never written to the AMI.
    token = urllib.request.urlopen(urllib.request.Request("http://169.254.169.254/latest/api/token",
        method="PUT", headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"}), timeout=2).read().decode()
    instance = urllib.request.urlopen(urllib.request.Request("http://169.254.169.254/latest/meta-data/instance-id",
        headers={"X-aws-ec2-metadata-token": token}), timeout=2).read().decode()
    metrics = [{"MetricName": key, "Value": float(values[key]),
        "Dimensions": [{"Name": "InstanceId", "Value": instance}]} for key in
        ("used_memory", "used_memory_rss", "connected_clients", "evicted_keys", "aof_rewrite_in_progress")]
    subprocess.run(["aws", "cloudwatch", "put-metric-data", "--region", os.environ["AWS_REGION"],
        "--namespace", "LabSeat/Redis", "--metric-data", json.dumps(metrics), "--no-cli-pager"],
        check=True, capture_output=True, timeout=15)


if __name__ == "__main__":
    try:
        collect()
    except Exception:
        print("Redis metric collection failed.", file=sys.stderr)
        sys.exit(1)
