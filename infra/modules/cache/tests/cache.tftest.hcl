mock_provider "aws" {}
variables {
  app_subnet_id               = "subnet-private"
  redis_sg_id                 = "sg-redis"
  redis_instance_profile_name = "redis-profile"
  redis_ami_id                = "ami-0123456789abcdef0"
}
run "require_compatibility_gate" {
  command         = plan
  expect_failures = [aws_instance.redis]
}
run "private_pinned_cache" {
  command = apply
  variables { compatibility_verified = true }
  assert {
    condition     = !aws_instance.redis.associate_public_ip_address && aws_instance.redis.instance_type == "t3.micro" && aws_instance.redis.root_block_device[0].encrypted && aws_instance.redis.root_block_device[0].volume_size == 20
    error_message = "Cache needs private t3.micro with encrypted 20 GiB EBS."
  }
  assert {
    condition     = output.redis_port == 6379 && output.redis_engine_version == "7.4.12" && !strcontains(aws_instance.redis.user_data, "PASSWORD")
    error_message = "Cache must pin the engine and fetch secrets at runtime."
  }
}
