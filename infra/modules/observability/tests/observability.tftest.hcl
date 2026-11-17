mock_provider "aws" {
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:us-east-1:123456789012:labseat-lab-workload" }
  }
}
variables {
  alb_arn_suffix          = "app/labseat/0123456789abcdef"
  target_group_arn_suffix = "targetgroup/web/0123456789abcdef"
  asg_name                = "web-asg"
  queue_name              = "notifications"
  dlq_name                = "notifications-dlq"
  cluster_name            = "cluster"
  api_service_name        = "api"
  db_instance_identifier  = "labseat-db"
  alarm_email             = "fixture@example.invalid"
}
run "application_monitoring" {
  command = apply
  assert {
    condition     = aws_cloudwatch_metric_alarm.workload.dimensions.TargetGroup == var.target_group_arn_suffix && aws_cloudwatch_metric_alarm.workload.datapoints_to_alarm == 2
    error_message = "ECS scaling and workload alarm must use the one ASG/TG."
  }
  assert {
    condition     = length(aws_cloudwatch_log_metric_filter.application) >= 20 && aws_cloudwatch_log_group.app.retention_in_days == 7
    error_message = "Booking/queue/lock/pool telemetry and log retention must be configured."
  }
}
run "redis_monitoring" {
  command = apply
  variables {
    redis_enabled     = true
    redis_instance_id = "i-0123456789abcdef0"
  }
  assert {
    condition     = strcontains(aws_cloudwatch_dashboard.labseat.dashboard_body, "LabSeat/Redis") && aws_cloudwatch_log_group.redis[0].retention_in_days == 7
    error_message = "Optional Redis retains its private metrics and logs."
  }
}

run "managed_redis_dashboard_has_valid_dimensions" {
  command = apply
  variables {
    redis_enabled          = true
    redis_instance_id      = null
    managed_cache_clusters = ["labseat-lab-001", "labseat-lab-002"]
  }
  assert {
    condition     = !strcontains(aws_cloudwatch_dashboard.labseat.dashboard_body, "LabSeat/Redis") && strcontains(aws_cloudwatch_dashboard.dependencies.dashboard_body, "AWS/ElastiCache")
    error_message = "Managed Redis must use cache cluster metrics without EC2 instance dimensions."
  }
  assert {
    condition     = alltrue([for widget in jsondecode(aws_cloudwatch_dashboard.labseat.dashboard_body).widgets : alltrue([for metric in widget.properties.metrics : alltrue([for value in metric : value != null])])])
    error_message = "Dashboard metric rows must not contain null dimensions."
  }
}
