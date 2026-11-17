locals {
  name = "${var.project}-${var.environment}-redis"
}
resource "aws_instance" "redis" {
  ami                         = var.redis_ami_id
  instance_type               = "t3.micro"
  subnet_id                   = var.app_subnet_id
  vpc_security_group_ids      = [var.redis_sg_id]
  iam_instance_profile        = var.redis_instance_profile_name
  associate_public_ip_address = false
  user_data_replace_on_change = false
  user_data                   = <<-SCRIPT
    #!/usr/bin/env bash
    set -euo pipefail
    install -d -m 0755 /etc/labseat-cache
    cat > /etc/labseat-cache/image.env <<'CONFIG'
    AWS_REGION=${var.region}
    PARAMETER_PREFIX=${var.parameter_prefix}
    REDIS_ENGINE_VERSION=${var.redis_engine_version}
    CONFIG
    chmod 0644 /etc/labseat-cache/image.env
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
      -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
    systemctl enable --now labseat-redis.service
    systemctl enable --now labseat-redis-metrics.timer
  SCRIPT
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    encrypted             = true
    delete_on_termination = true
  }
  tags = {
    Name               = local.name
    Project            = var.project
    Environment        = var.environment
    Owner              = "labseat"
    RedisEngineVersion = var.redis_engine_version
  }
  lifecycle {
    precondition {
      condition     = var.compatibility_verified
      error_message = "Verify the pinned engine, ACL, TLS and application compatibility before provisioning cache."
    }
  }
}
