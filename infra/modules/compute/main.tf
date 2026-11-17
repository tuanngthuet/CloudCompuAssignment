locals {
  name     = "${var.project}-${var.environment}"
  app_port = 8000

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

data "aws_ssm_parameter" "ecs_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2023/recommended/image_id"
}

resource "aws_lb" "app" {
  name               = "alb-${local.name}"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [var.alb_sg_id]
  subnets            = var.public_subnet_ids
  tags               = local.tags
}

resource "aws_lb_target_group" "app" {
  name                 = "${local.name}-app"
  port                 = local.app_port
  protocol             = "HTTP"
  target_type          = "ip"
  deregistration_delay = 30
  vpc_id               = var.vpc_id
  tags                 = local.tags

  health_check {
    path                = "/healthz"
    protocol            = "HTTP"
    port                = "traffic-port"
    matcher             = "200"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "http" {
  lifecycle {
    precondition {
      condition     = var.acm_certificate_arn != null || var.allow_http_demo
      error_message = "Provide an ACM certificate, or explicitly allow HTTP with synthetic data only."
    }
  }
  load_balancer_arn = aws_lb.app.arn
  port              = var.acm_certificate_arn != null ? 443 : 80
  protocol          = var.acm_certificate_arn != null ? "HTTPS" : "HTTP"
  certificate_arn   = var.acm_certificate_arn
  ssl_policy        = var.acm_certificate_arn != null ? "ELBSecurityPolicy-TLS13-1-2-2021-06" : null
  tags              = local.tags

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_launch_template" "app" {
  name          = "${local.name}-app"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.instance_type
  tags          = local.tags

  user_data = base64encode(<<-SCRIPT
    #!/bin/bash
    set -euo pipefail
    cat >> /etc/ecs/ecs.config <<'CONFIG'
    ECS_CLUSTER=${aws_ecs_cluster.app.name}
    ECS_RESERVED_MEMORY=384
    ECS_AWSVPC_BLOCK_IMDS=true
    ECS_ENABLE_TASK_IAM_ROLE=true
    CONFIG
  SCRIPT
  )

  iam_instance_profile {
    name = var.app_instance_profile_name
  }

  network_interfaces {
    device_index                = 0
    associate_public_ip_address = false
    delete_on_termination       = true
    security_groups             = [var.app_sg_id]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_type           = "gp3"
      volume_size           = 30
      encrypted             = true
      delete_on_termination = true
    }
  }

  monitoring {
    enabled = true
  }

  tag_specifications {
    resource_type = "volume"
    tags          = local.tags
  }
}

resource "aws_autoscaling_group" "app" {
  name                      = "${local.name}-app"
  vpc_zone_identifier       = var.app_subnet_ids
  min_size                  = var.capacity.min
  desired_capacity          = var.capacity.desired
  max_size                  = var.capacity.max
  health_check_type         = "EC2"
  health_check_grace_period = 120
  default_instance_warmup   = 120
  protect_from_scale_in     = true
  enabled_metrics           = ["GroupDesiredCapacity", "GroupInServiceInstances", "GroupTotalInstances"]

  launch_template {
    id      = aws_launch_template.app.id
    version = tostring(aws_launch_template.app.latest_version)
  }

  instance_refresh {
    strategy = "Rolling"

    preferences {
      # Keep refresh within the ASG capacity budget; drain old targets before replacement.
      min_healthy_percentage       = 50
      max_healthy_percentage       = 100
      skip_matching                = true
      scale_in_protected_instances = "Refresh"
    }
  }

  dynamic "tag" {
    for_each = merge(local.tags, { Name = "${local.name}-app", AmazonECSManaged = "true" })

    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  lifecycle {
    precondition {
      condition     = length(toset([for subnet in data.aws_subnet.app : subnet.availability_zone])) >= 2
      error_message = "Application ASG requires two distinct AZs."
    }
    precondition {
      condition     = alltrue([for subnet in data.aws_subnet.app : !subnet.map_public_ip_on_launch && subnet.vpc_id == var.vpc_id])
      error_message = "Application subnets must be private, without auto public IP, in the application VPC."
    }
    precondition {
      condition     = ceil(var.api_tasks.max * var.deployment_maximum_percent / 100) * var.db_pool_size + 4 * var.background_pool_size + (var.maintenance_enabled ? 1 : 0) + var.db_reserved_connections <= var.db_connection_budget
      error_message = "Rolling API tasks + background pools + migration/operator reserve exceed database budget."
    }
    # Terraform sets initial capacity; the scaling policy manages it afterwards.
    ignore_changes = [desired_capacity]

    precondition {
      condition     = length(setintersection(var.public_subnet_ids, var.app_subnet_ids)) == 0
      error_message = "The public ALB subnets and private app subnets must be disjoint."
    }
  }

  # The listener must associate the target group with the ALB before instance health is checked.
  depends_on = [aws_lb_listener.http]
}

# Public HTTP redirects only; application traffic has one forwarding target group.
resource "aws_lb_listener" "redirect" {
  count             = var.acm_certificate_arn != null ? 1 : 0
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# IDs alone do not prove AZ distribution or private routing. Inspect subnets at plan time.
data "aws_subnet" "app" {
  for_each = var.app_subnet_ids
  id       = each.value
}
