variable "maintenance_enabled" {
  type    = bool
  default = false
}
variable "maintenance_role_arn" {
  type    = string
  default = null
}
resource "aws_ecs_task_definition" "maintenance" {
  count                    = var.maintenance_enabled ? 1 : 0
  family                   = "${local.name}-maintenance"
  requires_compatibilities = ["EC2"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.maintenance_role_arn
  container_definitions = jsonencode([{
    name             = "app", image = var.image, essential = true, cpu = 256, memory = 512, user = "10001", stopTimeout = 60,
    command          = ["python", "-m", "app.maintenance", "--execute"], readonlyRootFilesystem = true,
    linuxParameters  = { initProcessEnabled = true, tmpfs = [{ containerPath = "/tmp", size = 64, mountOptions = ["nosuid", "noexec"] }] },
    environment      = [for k, v in merge(var.runtime_environment, { DB_POOL_SIZE = "1", DB_MAX_OVERFLOW = "0", PYTHONDONTWRITEBYTECODE = "1" }) : { name = k, value = v }],
    secrets          = [for k, v in var.runtime_secrets : { name = k, valueFrom = v } if k == "DATABASE_URL"],
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = var.log_group, awslogs-region = var.region, awslogs-stream-prefix = "maintenance" } }
  }])
  lifecycle {
    precondition {
      condition     = var.maintenance_role_arn != null
      error_message = "Scheduled maintenance requires its own scoped role."
    }
  }
}
resource "aws_iam_role" "maintenance_scheduler" {
  count              = var.maintenance_enabled ? 1 : 0
  name_prefix        = "labseat-scheduler-"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "scheduler.amazonaws.com" }, Condition = { StringEquals = { "aws:SourceAccount" = split(":", var.app_role_arn)[4] } } }] })
}
resource "aws_iam_role_policy" "maintenance_scheduler" {
  count = var.maintenance_enabled ? 1 : 0
  role  = aws_iam_role.maintenance_scheduler[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "ecs:RunTask", Resource = replace(aws_ecs_task_definition.maintenance[0].arn, "/:[0-9]+$/", ":*"), Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.app.arn } } },
    { Effect = "Allow", Action = "iam:PassRole", Resource = [var.execution_role_arn, var.maintenance_role_arn], Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } } }
  ] })
}
resource "aws_scheduler_schedule" "maintenance" {
  count               = var.maintenance_enabled ? 1 : 0
  name                = "${local.name}-maintenance"
  state               = var.bootstrap ? "DISABLED" : "ENABLED"
  schedule_expression = "rate(5 minutes)"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_ecs_cluster.app.arn
    role_arn = aws_iam_role.maintenance_scheduler[0].arn
    retry_policy {
      maximum_event_age_in_seconds = 600
      maximum_retry_attempts       = 2
    }
    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.maintenance[0].arn
      task_count          = 1
      capacity_provider_strategy {
        capacity_provider = aws_ecs_capacity_provider.app.name
        weight            = 1
      }
      network_configuration {
        subnets          = var.app_subnet_ids
        security_groups  = [var.app_sg_id]
        assign_public_ip = false
      }
    }
  }
}
output "maintenance_task_definition" { value = try(aws_ecs_task_definition.maintenance[0].arn, null) }

output "maintenance_schedule" { value = try(aws_scheduler_schedule.maintenance[0].name, null) }
