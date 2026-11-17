#!/usr/bin/env bash
set -euo pipefail
# Compile the pinned Redis source with TLS. No credentials are fetched while baking.
version=7.4.12
source_sha=56588ee1648539556f2b6cf4e873e3734afbbe40fa952fec2fcd6b6d7dae2924
dnf install -y gcc make openssl-devel tar gzip curl python3.12 awscli-2 amazon-cloudwatch-agent
curl -fsSL "https://download.redis.io/releases/redis-${version}.tar.gz" -o /tmp/labseat-redis-source.tar.gz
printf '%s  %s\n' "$source_sha" /tmp/labseat-redis-source.tar.gz | sha256sum -c -
tar -xzf /tmp/labseat-redis-source.tar.gz -C /tmp
make -C "/tmp/redis-${version}" -j2 BUILD_TLS=yes
make -C "/tmp/redis-${version}" install
getent group labseat-redis >/dev/null || groupadd --system labseat-redis
id labseat-redis >/dev/null 2>&1 || useradd --system --gid labseat-redis --shell /sbin/nologin labseat-redis
install -d -m 0755 /usr/local/libexec/labseat-cache /etc/labseat-cache
install -m 0644 /tmp/labseat-cache/bootstrap.py /tmp/labseat-cache/metrics.py /usr/local/libexec/labseat-cache/
install -m 0644 /tmp/labseat-cache/labseat-redis*.service /tmp/labseat-cache/labseat-redis*.timer /etc/systemd/system/
# Logs go to one pre-created group with an instance-specific stream.
cat >/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CONFIG'
{"logs":{"logs_collected":{"files":{"collect_list":[{"file_path":"/var/log/labseat-redis/server.log","log_group_name":"/labseat/lab/redis","log_stream_name":"{instance_id}"}]}}}}
CONFIG
systemctl enable amazon-cloudwatch-agent.service
systemd-analyze verify /etc/systemd/system/labseat-redis.service /etc/systemd/system/labseat-redis-metrics.service
rm -rf -- "/tmp/redis-${version}" /tmp/labseat-redis-source.tar.gz /tmp/labseat-cache
