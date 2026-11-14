output "db_endpoint" {
  description = "Private RDS endpoint in host:port form. Contains no credentials."
  value       = aws_db_instance.app.endpoint
}

output "db_name" {
  description = "Initial PostgreSQL database name."
  value       = aws_db_instance.app.db_name
}

output "db_instance_identifier" {
  description = "RDS identifier for CloudWatch dimensions and recovery."
  value       = aws_db_instance.app.identifier
}

output "app_bucket_name" {
  description = "Private app bucket name."
  value       = aws_s3_bucket.app.id
}

output "app_bucket_arn" {
  description = "App bucket ARN for the runtime IAM module."
  value       = aws_s3_bucket.app.arn
  depends_on = [
    aws_s3_bucket_public_access_block.app,
    aws_s3_bucket_ownership_controls.app,
    aws_s3_bucket_server_side_encryption_configuration.app,
    aws_s3_bucket_policy.require_tls,
  ]
}
