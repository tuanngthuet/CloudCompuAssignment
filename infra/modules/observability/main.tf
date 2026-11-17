locals {
  name                = "labseat-${var.environment}"
  workload_alarm_name = "${local.name}-requests-per-target-high"
  workload_threshold  = var.workload_threshold
  alb_dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.target_group_arn_suffix
  }

  # The SNS topic ARN gives us the deployment region and account for the same-region alarm.
  topic_arn_parts = split(":", aws_sns_topic.workload.arn)
  region          = local.topic_arn_parts[3]
  account_id      = local.topic_arn_parts[4]
  alarm_arn       = "arn:${local.topic_arn_parts[1]}:cloudwatch:${local.region}:${local.account_id}:alarm:${local.workload_alarm_name}"
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/labseat/${var.environment}/app"
  retention_in_days = 7
}

resource "aws_sns_topic" "workload" {
  name = "${local.name}-workload"
}

resource "aws_sns_topic_policy" "workload" {
  arn = aws_sns_topic.workload.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudWatchWorkloadAlarm"
      Effect    = "Allow"
      Principal = { Service = "cloudwatch.amazonaws.com" }
      Action    = "sns:Publish"
      Resource  = aws_sns_topic.workload.arn
      Condition = {
        ArnLike      = { "aws:SourceArn" = [local.alarm_arn, "arn:${local.topic_arn_parts[1]}:cloudwatch:${local.region}:${local.account_id}:alarm:${local.name}-*"] }
        StringEquals = { "aws:SourceAccount" = local.account_id }
      }
    }]
  })
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.workload.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "workload" {
  alarm_name          = local.workload_alarm_name
  alarm_description   = "Request count per healthy application target exceeded ${local.workload_threshold} in both of the last two minutes."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  namespace           = "AWS/ApplicationELB"
  metric_name         = "RequestCountPerTarget"
  dimensions          = local.alb_dimensions
  period              = 60
  statistic           = "Sum" # CloudWatch uses Sum for the per-target average published by ALB.
  threshold           = local.workload_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.workload.arn]

  depends_on = [aws_sns_topic_policy.workload]
}

resource "aws_cloudwatch_log_group" "redis" {
  count             = var.redis_enabled ? 1 : 0
  name              = "/labseat/${var.environment}/redis"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_metric_filter" "application" {
  for_each       = toset(["HoldSuccess", "HoldFailure", "ConfirmSuccess", "ConfirmFailure", "AdmissionGrant", "QueueWaitMs", "RedisLatencyMs", "RedisFailure", "BookingLockMs", "PoolCheckedOut", "PoolAcquireMs", "RedisAvailable", "OutboxPending", "OutboxPublishFailure", "OutboxPublished", "OutboxLoopFailure", "WorkerFailure", "EmailAttempt", "EmailAccepted", "EmailDuplicateSuppressed", "DBQueryError", "DBTransactionMs", "MaintenanceSuccess", "MaintenanceFailure", "GarbageCollectionFailure", "EmailUnknown"])
  name           = "${local.name}-${each.value}"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ $.metric = \"${each.value}\" }"
  metric_transformation {
    name      = each.value
    namespace = "LabSeat/Application"
    value     = "$.value"
  }
}
