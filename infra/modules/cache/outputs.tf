output "redis_endpoint" { value = aws_instance.redis.private_dns }
output "redis_port" { value = 6379 }
output "redis_instance_id" { value = aws_instance.redis.id }
output "redis_data_volume_id" { value = aws_instance.redis.root_block_device[0].volume_id }
output "redis_engine_version" { value = var.redis_engine_version }
output "redis_ca_parameter_name" { value = "${var.parameter_prefix}CA_CERT" }
