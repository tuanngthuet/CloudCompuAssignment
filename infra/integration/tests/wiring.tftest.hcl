override_data {
  target = module.compute.data.aws_subnet.app["subnet-001a"]
  values = { availability_zone = "us-east-1a", vpc_id = "vpc-0123456789abcdef0", map_public_ip_on_launch = false }
}
override_data {
  target = module.compute.data.aws_subnet.app["subnet-001b"]
  values = { availability_zone = "us-east-1b", vpc_id = "vpc-0123456789abcdef0", map_public_ip_on_launch = false }
}
# All provider operations are mocked. No AWS calls or credentials.
mock_provider "aws" {
  mock_resource "aws_autoscaling_group" { defaults = { arn = "arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:11111111-1111-1111-1111-111111111111:autoScalingGroupName/labseat-lab-app" } }
  mock_resource "aws_ecs_cluster" { defaults = { id = "arn:aws:ecs:us-east-1:123456789012:cluster/labseat-lab", arn = "arn:aws:ecs:us-east-1:123456789012:cluster/labseat-lab" } }
  mock_resource "aws_ecs_task_definition" { defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/labseat:1" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/task" } }
  mock_resource "aws_sqs_queue" { defaults = { arn = "arn:aws:sqs:us-east-1:123456789012:notifications" } }

  mock_data "aws_partition" { defaults = { partition = "aws" } }
  mock_data "aws_ssm_parameter" { defaults = { value = "ami-0123456789abcdef0" } }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/labseat/0123456789abcdef", arn_suffix = "app/labseat/0123456789abcdef" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/labseat/0123456789abcdef", arn_suffix = "targetgroup/labseat/0123456789abcdef" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/labseat/0123456789abcdef/0123456789abcdef" }
  }
  mock_resource "aws_launch_template" { defaults = { id = "lt-0123456789abcdef0", latest_version = 1 } }
  mock_resource "aws_sns_topic" { defaults = { arn = "arn:aws:sns:us-east-1:123456789012:labseat-lab-workload" } }
  mock_resource "aws_s3_bucket" { defaults = { arn = "arn:aws:s3:::labseat-fixture-bucket", id = "labseat-fixture-bucket" } }
  mock_resource "aws_cloudwatch_log_group" { defaults = { arn = "arn:aws:logs:us-east-1:123456789012:log-group:/labseat/lab/mock" } }
}
variables {
  allow_http_demo     = true
  expected_account_id = "123456789012"
  image               = "123456789012.dkr.ecr.us-east-1.amazonaws.com/labseat-lab@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  alarm_email         = "fixture@example.invalid"
  network = {
    vpc_id            = "vpc-0123456789abcdef0"
    public_subnet_ids = ["subnet-000a", "subnet-000b"]
    app_subnet_ids    = ["subnet-001a", "subnet-001b"]
    db_subnet_ids     = ["subnet-002a", "subnet-002b"]
    alb_sg_id         = "sg-0001"
    app_sg_id         = "sg-0002"
    db_sg_id          = "sg-0003"
    redis_sg_id       = "sg-0005"
  }
}
run "application_without_cache" {
  command = apply
  assert {
    condition     = output.redis_endpoint == null && output.asg_name != null && output.target_group_arn != null
    error_message = "LABSEAT application works with queue dependency unprovisioned."
  }
}
run "application_with_cache" {
  command = apply
  variables {
    redis_enabled                = true
    cache_compatibility_verified = true
    redis_ami_id                 = "ami-0123456789abcdef0"
  }
  assert {
    condition     = output.asg_name == run.application_without_cache.asg_name && output.redis_instance_id != null && output.db_endpoint == run.application_without_cache.db_endpoint
    error_message = "Enabling cache retains application and database resources."
  }
}

run "production_managed_cache" {
  command = apply
  variables {
    production              = true
    managed_redis           = true
    redis_enabled           = true
    redis_auth_token        = "fixture-runtime-password-only"
    redis_operator_password = "fixture-operator-password-only"
  }
  assert {
    condition     = module.data.db_endpoint != null && length(module.cache) == 0 && output.redis_endpoint != null
    error_message = "Production managed cache replaces only cache implementation, not application capacity."
  }
}

run "brevo_provider_configuration" {
  command = apply
  variables {
    email_backend         = "brevo"
    brevo_from_email      = "labseat@example.invalid"
    email_public_base_url = "https://labseat.example.invalid"
  }
  assert {
    condition     = output.services.worker != null && output.cluster_name != null
    error_message = "Brevo runs on the existing worker/cluster with an injected Brevo API key."
  }
}

run "platform_realtime_and_maintenance" {
  command = apply
  variables {
    realtime_enabled        = true
    redis_enabled           = true
    managed_redis           = true
    redis_auth_token        = "fixture-runtime-password-only"
    redis_operator_password = "fixture-operator-password-only"
    redis_events_password   = "fixture-events-password-only"
  }
  assert {
    condition     = module.compute.maintenance_task_definition != null && module.compute.maintenance_schedule != null && output.redis_endpoint != null
    error_message = "Scheduled maintenance and separately scoped Pub/Sub must be provisioned."
  }
}
