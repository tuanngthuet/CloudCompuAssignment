output "app_instance_profile_name" {
  description = "Instance profile name for the compute launch template."
  value       = aws_iam_instance_profile.app.name
  depends_on  = [aws_iam_role_policy.runtime]
}
