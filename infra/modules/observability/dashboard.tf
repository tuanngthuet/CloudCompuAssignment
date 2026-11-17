resource "aws_cloudwatch_dashboard" "labseat" {
  dashboard_name = "${local.name}-operations"

  dashboard_body = jsonencode({
    periodOverride = "inherit"
    widgets = concat([
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          region = local.region
          title  = "Requests per target per minute"
          period = 60
          stat   = "Sum"
          metrics = [
            ["AWS/ApplicationELB", "RequestCountPerTarget", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix],
          ]
          annotations = {
            horizontal = [{ label = "SNS workload alarm", value = local.workload_threshold }]
          }
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          region = local.region
          title  = "Healthy application targets"
          period = 60
          stat   = "Minimum"
          metrics = [
            ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix],
            ["AWS/ApplicationELB", "UnHealthyHostCount", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          region = local.region
          title  = "Target response time p95 (seconds)"
          period = 60
          stat   = "p95"
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          region = local.region
          title  = "HTTP 5xx responses per minute"
          period = 60
          stat   = "Sum"
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", var.alb_arn_suffix, { label = "ALB" }],
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix, "TargetGroup", var.target_group_arn_suffix, { label = "Application targets" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 12, height = 6
        properties = {
          region = local.region
          title  = "EC2 average CPU utilization (%)"
          period = 60
          stat   = "Average"
          metrics = [
            ["AWS/EC2", "CPUUtilization", "AutoScalingGroupName", var.asg_name],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 12, width = 12, height = 6
        properties = {
          region = local.region
          title  = "Auto Scaling capacity"
          period = 60
          stat   = "Average"
          metrics = [
            ["AWS/AutoScaling", "GroupDesiredCapacity", "AutoScalingGroupName", var.asg_name, { label = "Desired" }],
            ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", var.asg_name, { label = "In service" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 18, width = 12, height = 6
        properties = {
          region = local.region
          title  = "RDS client connections"
          period = 60
          stat   = "Maximum"
          metrics = [
            ["AWS/RDS", "DatabaseConnections", "DBInstanceIdentifier", var.db_instance_identifier],
          ]
        }
      },
      ], var.redis_enabled && var.redis_instance_id != null ? [
      {
        type = "metric", x = 12, y = 18, width = 12, height = 6
        properties = {
          region = local.region, title = "Redis memory / clients / CPU", period = 60, stat = "Maximum"
          metrics = [
            ["LabSeat/Redis", "used_memory_rss", "InstanceId", var.redis_instance_id],
            ["LabSeat/Redis", "used_memory", "InstanceId", var.redis_instance_id],
            ["LabSeat/Redis", "connected_clients", "InstanceId", var.redis_instance_id, { yAxis = "right" }],
            ["AWS/EC2", "CPUUtilization", "InstanceId", var.redis_instance_id, { stat = "Average", yAxis = "right" }]
          ]
        }
      }
      ] : [], [
      {
        type = "metric", x = 0, y = 24, width = 24, height = 6
        properties = {
          region = local.region, title = "Booking, queue and pool telemetry", period = 60, stat = "Sum"
          metrics = [for name in ["HoldSuccess", "HoldFailure", "ConfirmSuccess", "ConfirmFailure", "AdmissionGrant", "QueueWaitMs", "RedisLatencyMs", "BookingLockMs", "PoolCheckedOut", "PoolAcquireMs", "RedisAvailable"] : ["LabSeat/Application", name, {
            stat = contains(["QueueWaitMs", "RedisLatencyMs", "BookingLockMs", "PoolAcquireMs"], name) ? "p95" : name == "PoolCheckedOut" ? "Maximum" : name == "RedisAvailable" ? "Minimum" : "Sum"
          }]]
        }
      }
    ])
  })
}
