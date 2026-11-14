locals {
  name     = "${var.project}-${var.environment}"
  app_port = 8000

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# Read the supplied release AMI to override its root volume at the correct device.
data "aws_ami" "app" {
  filter {
    name   = "image-id"
    values = [var.ami_id]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
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
  name        = "${local.name}-app"
  port        = local.app_port
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = var.vpc_id
  tags        = local.tags

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
  load_balancer_arn = aws_lb.app.arn
  port              = 80
  protocol          = "HTTP"
  tags              = local.tags

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app.arn
  }
}

resource "aws_launch_template" "app" {
  name          = "${local.name}-app"
  image_id      = data.aws_ami.app.id
  instance_type = "t3.small"
  tags          = local.tags

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
    device_name = data.aws_ami.app.root_device_name

    ebs {
      volume_type           = "gp3"
      volume_size           = 20
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
  target_group_arns         = [aws_lb_target_group.app.arn]
  min_size                  = 2
  desired_capacity          = 2
  max_size                  = 4
  health_check_type         = "ELB"
  health_check_grace_period = 120
  default_instance_warmup   = 120
  min_elb_capacity          = 2
  enabled_metrics           = ["GroupDesiredCapacity", "GroupInServiceInstances", "GroupTotalInstances"]

  launch_template {
    id      = aws_launch_template.app.id
    version = tostring(aws_launch_template.app.latest_version)
  }

  instance_refresh {
    strategy = "Rolling"

    preferences {
      # AWS launches a healthy replacement before removing each old instance.
      min_healthy_percentage = 100
      max_healthy_percentage = 100
      skip_matching          = true
    }
  }

  dynamic "tag" {
    for_each = merge(local.tags, { Name = "${local.name}-app" })

    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  lifecycle {
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
