#!/usr/bin/env bash
set -euo pipefail

dnf install -y python3.12 python3.12-pip awscli-2 amazon-cloudwatch-agent logrotate
getent group labseat >/dev/null || groupadd --system labseat
id labseat >/dev/null 2>&1 || useradd --system --gid labseat --shell /sbin/nologin labseat

install -d -m 0755 /opt/labseat/app /etc/labseat /usr/local/libexec/labseat
cp -R /tmp/labseat-app/. /opt/labseat/app/
chown -R root:root /opt/labseat/app
chmod -R a+rX,go-w /opt/labseat/app
/usr/bin/python3.12 -m venv /opt/labseat/venv
/opt/labseat/venv/bin/pip install --no-cache-dir -r /opt/labseat/app/requirements.lock

install -m 0644 /tmp/labseat-deploy/labseat.service /etc/systemd/system/labseat.service
install -m 0644 /tmp/labseat-deploy/launch.py /usr/local/libexec/labseat/launch.py
install -m 0644 /tmp/labseat-deploy/labseat.logrotate /etc/logrotate.d/labseat
install -d -o labseat -g labseat -m 0750 /var/log/labseat
install -o labseat -g labseat -m 0640 /dev/null /var/log/labseat/app.log
printf 'LABSEAT_IMAGE_MODE=%s\nAPP_VERSION=%s\nAWS_REGION=%s\n' \
    "$LABSEAT_IMAGE_MODE" "$APP_VERSION" "$AWS_REGION" >/etc/labseat/image.env
chmod 0644 /etc/labseat/image.env

if [[ "$LABSEAT_IMAGE_MODE" == release ]]; then
    install -d -m 0755 /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d
    install -m 0644 /tmp/labseat-deploy/cloudwatch-agent.json \
        /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/file_labseat.json
    systemctl enable amazon-cloudwatch-agent.service
fi

systemd-analyze verify /etc/systemd/system/labseat.service
systemctl enable labseat.service
rm -rf -- /tmp/labseat-app /tmp/labseat-deploy
