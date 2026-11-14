output "alb_url" {
  description = "HTTP endpoint for the LabSeat lab deployment using test data."
  value       = "http://${aws_lb.app.dns_name}"
}

output "alb_arn_suffix" {
  description = "ALB ARN suffix used for CloudWatch dimensions and the target tracking resource label."
  value       = aws_lb.app.arn_suffix
}

output "target_group_arn_suffix" {
  description = "Target group ARN suffix used for CloudWatch dimensions and the target tracking resource label."
  value       = aws_lb_target_group.app.arn_suffix
}

output "asg_name" {
  description = "Auto Scaling group name for the scaling policy and CloudWatch dimensions."
  value       = aws_autoscaling_group.app.name
}

output "launch_template_id" {
  description = "EC2 launch template ID for release verification."
  value       = aws_launch_template.app.id
}

output "launch_template_version" {
  description = "Numeric launch template version selected in the Auto Scaling group."
  value       = aws_launch_template.app.latest_version
}

output "target_group_arn" {
  description = "Target group ARN for verifying target health through AWS CLI."
  value       = aws_lb_target_group.app.arn
}
