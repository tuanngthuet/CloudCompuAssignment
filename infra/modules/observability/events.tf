variable "queue_name" { type = string }
variable "dlq_name" { type = string }
variable "cluster_name" { type = string }
variable "api_service_name" { type = string }
resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${local.name}-dlq"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  threshold           = 0
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = var.dlq_name }
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.workload.arn]
}
resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${local.name}-queue-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  threshold           = 300
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = var.queue_name }
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.workload.arn]
}
resource "aws_cloudwatch_metric_alarm" "outbox" {
  alarm_name          = "${local.name}-outbox-backlog"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  threshold           = 100
  namespace           = "LabSeat/Application"
  metric_name         = "OutboxPending"
  period              = 60
  statistic           = "Maximum"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.workload.arn]
}
resource "aws_cloudwatch_dashboard" "events" {
  dashboard_name = "${local.name}-ecs-events"
  dashboard_body = jsonencode({ widgets = [{ type = "metric", x = 0, y = 0, width = 24, height = 6, properties = {
    region = local.region, title = "ECS and asynchronous pipeline", period = 60, stat = "Maximum",
    metrics = [
      ["ECS/ContainerInsights", "RunningTaskCount", "ClusterName", var.cluster_name, "ServiceName", var.api_service_name],
      ["ECS/ContainerInsights", "PendingTaskCount", "ClusterName", var.cluster_name, "ServiceName", var.api_service_name],
      ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", var.queue_name],
      ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.dlq_name],
      ["LabSeat/Application", "OutboxPending"], ["LabSeat/Application", "WorkerFailure", { stat = "Sum" }]
    ]
  } }] })
}
variable "db_connection_budget" { default = 66 }
variable "managed_cache_clusters" {
  type    = set(string)
  default = []
}
locals {
  dependency_alarms = {
    alb_5xx              = { namespace = "AWS/ApplicationELB", metric = "HTTPCode_Target_5XX_Count", dimensions = { LoadBalancer = var.alb_arn_suffix }, threshold = 10, statistic = "Sum", comparison = "GreaterThanThreshold" }
    alb_latency          = { namespace = "AWS/ApplicationELB", metric = "TargetResponseTime", dimensions = { LoadBalancer = var.alb_arn_suffix }, threshold = 1, statistic = "Average", comparison = "GreaterThanThreshold" }
    alb_unhealthy        = { namespace = "AWS/ApplicationELB", metric = "UnHealthyHostCount", dimensions = local.alb_dimensions, threshold = 0, statistic = "Maximum", comparison = "GreaterThanThreshold" }
    db_connections       = { namespace = "AWS/RDS", metric = "DatabaseConnections", dimensions = { DBInstanceIdentifier = var.db_instance_identifier }, threshold = floor(var.db_connection_budget * 0.8), statistic = "Maximum", comparison = "GreaterThanThreshold" }
    redis_unavailable    = { namespace = "LabSeat/Application", metric = "RedisAvailable", dimensions = {}, threshold = 1, statistic = "Minimum", comparison = "LessThanThreshold" }
    maintenance_failures = { namespace = "LabSeat/Application", metric = "MaintenanceFailure", dimensions = {}, threshold = 0, statistic = "Sum", comparison = "GreaterThanThreshold" }
    gc_failures          = { namespace = "LabSeat/Application", metric = "GarbageCollectionFailure", dimensions = {}, threshold = 0, statistic = "Sum", comparison = "GreaterThanThreshold" }
    email_unknown        = { namespace = "LabSeat/Application", metric = "EmailUnknown", dimensions = {}, threshold = 0, statistic = "Sum", comparison = "GreaterThanThreshold" }
    worker_failures      = { namespace = "LabSeat/Application", metric = "WorkerFailure", dimensions = {}, threshold = 0, statistic = "Sum", comparison = "GreaterThanThreshold" }
  }
}
resource "aws_cloudwatch_metric_alarm" "dependency" {
  for_each            = local.dependency_alarms
  alarm_name          = "${local.name}-${each.key}"
  comparison_operator = each.value.comparison
  evaluation_periods  = 2
  threshold           = each.value.threshold
  namespace           = each.value.namespace
  metric_name         = each.value.metric
  dimensions          = each.value.dimensions
  period              = 60
  statistic           = each.value.statistic
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.workload.arn]
}
resource "aws_cloudwatch_dashboard" "dependencies" {
  dashboard_name = "${local.name}-dependencies"
  dashboard_body = jsonencode({ widgets = concat([
    { type = "metric", x = 0, y = 0, width = 24, height = 6, properties = {
      region = local.region, title = "ECS and DB resource usage", period = 60, stat = "Maximum", metrics = [
        ["AWS/ECS", "CPUUtilization", "ClusterName", var.cluster_name, "ServiceName", var.api_service_name],
        ["AWS/ECS", "MemoryUtilization", "ClusterName", var.cluster_name, "ServiceName", var.api_service_name],
        ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.db_instance_identifier],
        ["AWS/RDS", "Deadlocks", "DBInstanceIdentifier", var.db_instance_identifier, { stat = "Sum" }],
        ["LabSeat/Application", "DBTransactionMs", { stat = "p95" }],
        ["LabSeat/Application", "DBQueryError", { stat = "Sum" }]
      ]
    } }
    ], [for cluster in var.managed_cache_clusters : {
      type = "metric", x = 0, y = 6, width = 24, height = 6, properties = {
        region = local.region, title = "Managed Redis ${cluster}", period = 60, stat = "Maximum", metrics = [
          ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "CacheClusterId", cluster],
          ["AWS/ElastiCache", "CurrConnections", "CacheClusterId", cluster],
          ["AWS/ElastiCache", "EngineCPUUtilization", "CacheClusterId", cluster],
          ["AWS/ElastiCache", "Evictions", "CacheClusterId", cluster, { stat = "Sum" }],
          ["AWS/ElastiCache", "ReplicationLag", "CacheClusterId", cluster]
        ]
      }
  }]) })
}

variable "maintenance_enabled" {
  type    = bool
  default = false
}
resource "aws_cloudwatch_metric_alarm" "maintenance_missing" {
  count               = var.maintenance_enabled ? 1 : 0
  alarm_name          = "${local.name}-maintenance-missing"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  threshold           = 1
  namespace           = "LabSeat/Application"
  metric_name         = "MaintenanceSuccess"
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.workload.arn]
}
