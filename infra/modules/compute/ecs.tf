resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
resource "aws_ecs_cluster" "app" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_ecs_capacity_provider" "app" {
  name = local.name
  auto_scaling_group_provider {
    auto_scaling_group_arn         = aws_autoscaling_group.app.arn
    managed_termination_protection = "ENABLED"
    managed_draining               = "ENABLED"
    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = var.target_capacity
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 2
      instance_warmup_period    = 120
    }
  }
}
resource "aws_ecs_cluster_capacity_providers" "app" {
  cluster_name       = aws_ecs_cluster.app.name
  capacity_providers = [aws_ecs_capacity_provider.app.name]
  default_capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.app.name
    weight            = 1
    base              = 0
  }
}
locals {
  roles    = { api = var.app_role_arn, worker = var.worker_role_arn, publisher = var.publisher_role_arn }
  commands = { api = ["python", "-m", "app.start"], worker = ["python", "-m", "app.events", "worker"], publisher = ["python", "-m", "app.events", "publisher"] }
}
resource "aws_ecs_task_definition" "app" {
  for_each                 = local.roles
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["EC2"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = each.value
  container_definitions = jsonencode([{
    name                   = "app"
    image                  = var.image
    essential              = true
    command                = local.commands[each.key]
    cpu                    = 256
    memory                 = 512
    user                   = "10001"
    stopTimeout            = 60
    readonlyRootFilesystem = true
    linuxParameters        = { initProcessEnabled = true, tmpfs = [{ containerPath = "/tmp", size = 64, mountOptions = ["nosuid", "noexec"] }] }
    portMappings           = each.key == "api" ? [{ containerPort = 8000, protocol = "tcp" }] : []
    environment            = [for k, v in merge(var.runtime_environment, { DB_POOL_SIZE = tostring(each.key == "api" ? var.db_pool_size : var.background_pool_size), DB_MAX_OVERFLOW = "0", COOKIE_SECURE = tostring(var.acm_certificate_arn != null), PORT = "8000", PYTHONDONTWRITEBYTECODE = "1" }) : { name = k, value = v }]
    secrets                = [for k, v in var.runtime_secrets : { name = k, valueFrom = v } if(each.key == "api" && k != "BREVO_API_KEY") || k == "DATABASE_URL" || (each.key == "worker" && contains(["BREVO_API_KEY", "AUTH_LINK_SIGNING_KEY"], k)) || (each.key == "publisher" && contains(["REDIS_EVENTS_URL", "REDIS_EVENTS_USERNAME", "REDIS_EVENTS_PASSWORD", "REDIS_CA_CERT"], k))]
    logConfiguration       = { logDriver = "awslogs", options = { awslogs-group = var.log_group, awslogs-region = var.region, awslogs-stream-prefix = each.key } }
    healthCheck            = each.key == "api" ? { command = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"], interval = 30, timeout = 5, retries = 3, startPeriod = 20 } : null
  }])
}
resource "aws_ecs_service" "app" {
  for_each                           = local.roles
  name                               = "${local.name}-${each.key}"
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.app[each.key].arn
  desired_count                      = var.bootstrap ? 0 : (each.key == "api" ? var.api_tasks.min : 1)
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = var.deployment_maximum_percent
  health_check_grace_period_seconds  = each.key == "api" ? 30 : null
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  capacity_provider_strategy {
    capacity_provider = aws_ecs_capacity_provider.app.name
    weight            = 1
  }
  network_configuration {
    subnets          = var.app_subnet_ids
    security_groups  = [var.app_sg_id]
    assign_public_ip = false
  }
  ordered_placement_strategy {
    type  = "spread"
    field = "attribute:ecs.availability-zone"
  }
  ordered_placement_strategy {
    type  = "binpack"
    field = "memory"
  }
  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.app.arn
      container_name   = "app"
      container_port   = 8000
    }
  }
  lifecycle { ignore_changes = [desired_count, task_definition] }
  depends_on = [aws_lb_listener.http, aws_ecs_cluster_capacity_providers.app]
}
resource "aws_appautoscaling_target" "api" {
  max_capacity       = var.api_tasks.max
  min_capacity       = var.bootstrap ? 0 : var.api_tasks.min
  resource_id        = "service/${aws_ecs_cluster.app.name}/${aws_ecs_service.app["api"].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
resource "aws_appautoscaling_policy" "api" {
  for_each           = { cpu = "ECSServiceAverageCPUUtilization", memory = "ECSServiceAverageMemoryUtilization", requests = "ALBRequestCountPerTarget" }
  name               = "${local.name}-${each.key}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = "ecs"
  target_tracking_scaling_policy_configuration {
    target_value       = each.key == "requests" ? var.requests_per_target : 65
    scale_in_cooldown  = 180
    scale_out_cooldown = 60
    predefined_metric_specification {
      predefined_metric_type = each.value
      resource_label         = each.key == "requests" ? "${aws_lb.app.arn_suffix}/${aws_lb_target_group.app.arn_suffix}" : null
    }
  }
}
output "cluster_name" { value = aws_ecs_cluster.app.name }
output "capacity_provider" { value = aws_ecs_capacity_provider.app.name }
output "repository_url" { value = aws_ecr_repository.app.repository_url }
output "services" { value = { for k, s in aws_ecs_service.app : k => s.name } }
output "task_definitions" { value = { for k, t in aws_ecs_task_definition.app : k => t.arn } }
