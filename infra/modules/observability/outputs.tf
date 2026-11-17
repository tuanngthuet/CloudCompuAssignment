output "dashboard_name" {
  description = "Name of the CloudWatch operations dashboard."
  value       = aws_cloudwatch_dashboard.labseat.dashboard_name
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for the separate workload alarm."
  value       = aws_sns_topic.workload.arn
}

output "log_group_name" {
  description = "Name of the application log group with seven-day retention."
  value       = aws_cloudwatch_log_group.app.name
}

output "log_group_arn" {
  description = "ARN of the application log group."
  value       = aws_cloudwatch_log_group.app.arn
}

output "workload_alarm_name" {
  description = "Name of the CloudWatch alarm for workload notifications."
  value       = aws_cloudwatch_metric_alarm.workload.alarm_name
}

output "redis_log_group_arn" {
  value = try(aws_cloudwatch_log_group.redis[0].arn, null)
}
