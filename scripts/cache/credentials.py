"""Create private local parameter files for operator upload; never print their contents."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets

RUNTIME_COMMANDS = "+ping +hello +client|setinfo +info +evalsha +script|load +time +get +type +incr +zadd +zrem +zrange +zrangebyscore +zcount +zcard +zrank +hget +hset +hlen +hdel +expire +pexpire +pexpireat +exists +zscore +del"


def acl(runtime, operator, monitor, events=None):
    password_hash = lambda value: "#" + hashlib.sha256(value.encode()).hexdigest()
    lines = [
        "user default off",
        f"user runtime on {password_hash(runtime)} ~labseat:queue:* -@all {RUNTIME_COMMANDS}",
        f"user operator on {password_hash(operator)} ~labseat:queue:* -@all {RUNTIME_COMMANDS} +set +scan +unlink",
        f"user monitor on {password_hash(monitor)} -@all +info +ping",
    ]
    if events:
        lines.append(f"user events on {password_hash(events)} &labseat:events:* -@all +ping +hello +publish +subscribe +unsubscribe")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--ca", type=Path, required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9.-]+", args.endpoint):
        parser.error("Use the private Redis DNS name that matches the certificate SAN.")
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    runtime, operator, monitor, events = [secrets.token_urlsafe(32) for _ in range(4)]
    values = {
        "cache-CA_CERT": ("cache/CA_CERT", args.ca.read_text(), "String"),
        "cache-SERVER_CERT": ("cache/SERVER_CERT", args.cert.read_text(), "String"),
        "cache-SERVER_KEY": ("cache/SERVER_KEY", args.key.read_text(), "SecureString"),
        "cache-ACL_FILE": ("cache/ACL_FILE", acl(runtime, operator, monitor, events), "SecureString"),
        "cache-MONITOR_PASSWORD": ("cache/MONITOR_PASSWORD", monitor, "SecureString"),
        "REDIS_URL": ("REDIS_URL", f"rediss://{args.endpoint}:6379/0", "String"),
        "REDIS_CA_CERT": ("REDIS_CA_CERT", args.ca.read_text(), "String"),
        "REDIS_USERNAME": ("REDIS_USERNAME", "runtime", "String"),
        "REDIS_PASSWORD": ("REDIS_PASSWORD", runtime, "SecureString"),
        "REDIS_EVENTS_URL": ("REDIS_EVENTS_URL", f"rediss://{args.endpoint}:6379/0", "String"),
        "REDIS_EVENTS_USERNAME": ("REDIS_EVENTS_USERNAME", "events", "String"),
        "REDIS_EVENTS_PASSWORD": ("REDIS_EVENTS_PASSWORD", events, "SecureString"),
        # Operator credentials use a distinct path excluded from runtime profiles.
        "operator-REDIS_USERNAME": ("operator/REDIS_USERNAME", "operator", "String"),
        "operator-REDIS_PASSWORD": ("operator/REDIS_PASSWORD", operator, "SecureString"),
    }
    for filename, (name, value, kind) in values.items():
        path = args.out / (filename + ".json")
        path.touch(mode=0o600)
        path.write_text(json.dumps({"Name": "/labseat/lab/" + name, "Type": kind, "Value": value}))
    print("Private parameter files created. Upload through the approved operator process; do not commit them.")


if __name__ == "__main__":
    main()
