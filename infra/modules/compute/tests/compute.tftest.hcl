override_data {
  target = data.aws_subnet.app["subnet-app-a"]
  values = { availability_zone = "us-east-1a", vpc_id = "vpc-0123456789abcdef0", map_public_ip_on_launch = false }
}
override_data {
  target = data.aws_subnet.app["subnet-app-b"]
  values = { availability_zone = "us-east-1b", vpc_id = "vpc-0123456789abcdef0", map_public_ip_on_launch = false }
}
mock_provider "aws" {
  mock_resource "aws_autoscaling_group" { defaults = { arn = "arn:aws:autoscaling:us-east-1:123456789012:autoScalingGroup:11111111-1111-1111-1111-111111111111:autoScalingGroupName/labseat-lab-app" } }
  mock_resource "aws_ecs_cluster" { defaults = { id = "arn:aws:ecs:us-east-1:123456789012:cluster/labseat-lab", arn = "arn:aws:ecs:us-east-1:123456789012:cluster/labseat-lab" } }
  mock_resource "aws_ecs_task_definition" { defaults = { arn = "arn:aws:ecs:us-east-1:123456789012:task-definition/labseat:1" } }
  mock_resource "aws_iam_role" { defaults = { arn = "arn:aws:iam::123456789012:role/task" } }
  mock_resource "aws_sqs_queue" { defaults = { arn = "arn:aws:sqs:us-east-1:123456789012:notifications" } }

  mock_resource "aws_launch_template" {
    defaults = { id = "lt-0123456789abcdef0", latest_version = 1 }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/labseat/0123456789abcdef" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/labseat/0123456789abcdef" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/app/labseat/0123456789abcdef/0123456789abcdef" }
  }
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }

}
variables {
  vpc_id                    = "vpc-0123456789abcdef0"
  public_subnet_ids         = ["subnet-public-a", "subnet-public-b"]
  app_subnet_ids            = ["subnet-app-a", "subnet-app-b"]
  alb_sg_id                 = "sg-alb"
  app_sg_id                 = "sg-web"
  app_instance_profile_name = "web-profile"
  image                     = "registry.invalid/labseat@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  execution_role_arn        = "arn:aws:iam::123456789012:role/execution"
  app_role_arn              = "arn:aws:iam::123456789012:role/api"
  worker_role_arn           = "arn:aws:iam::123456789012:role/worker"
  publisher_role_arn        = "arn:aws:iam::123456789012:role/publisher"
  log_group                 = "/labseat/lab/app"
  region                    = "us-east-1"
  runtime_environment       = {}
  runtime_secrets           = { DATABASE_URL = "arn:aws:ssm:us-east-1:123456789012:parameter/labseat/lab/DATABASE_URL" }
  allow_http_demo           = true
}
run "private_app" {
  command = apply
  assert {
    condition     = aws_autoscaling_group.app.min_size == 2 && aws_autoscaling_group.app.max_size == 6 && aws_lb_target_group.app.target_type == "ip" && aws_ecs_capacity_provider.app.auto_scaling_group_provider[0].managed_scaling[0].status == "ENABLED"
    error_message = "Exactly one application group uses 2/2/6 and one target group."
  }
  assert {
    condition     = !aws_launch_template.app.network_interfaces[0].associate_public_ip_address && strcontains(base64decode(aws_launch_template.app.user_data), "ECS_RESERVED_MEMORY=384")
    error_message = "API nodes are private and use the bounded common runtime."
  }
}
run "optional_redis_same_compute" {
  command = apply
  variables { redis_enabled = true }
  assert {
    condition     = output.asg_name == run.private_app.asg_name && length(aws_ecs_service.app) == 3
    error_message = "Redis configuration must not add a second application group."
  }
}
run "reject_excess_database_connections" {
  command = plan
  variables { db_connection_budget = 30 }
  expect_failures = [aws_autoscaling_group.app]
}
run "https" {
  command = apply
  variables { acm_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/fixture" }
  assert {
    condition     = aws_lb_listener.http.protocol == "HTTPS" && aws_lb_listener.http.port == 443 && length(aws_lb_listener.redirect) == 1
    error_message = "HTTPS forwards to the only application TG; HTTP redirects."
  }
}
run "reject_implicit_plain_http" {
  command = plan
  variables { allow_http_demo = false }
  expect_failures = [aws_lb_listener.http]
}

run "first_deployment_stays_stopped" {
  state_key = "bootstrap"
  command   = apply
  variables { bootstrap = true }
  assert {
    condition     = alltrue([for service in aws_ecs_service.app : service.desired_count == 0]) && aws_appautoscaling_target.api.min_capacity == 0
    error_message = "First deployment cannot serve before one-off migration."
  }
}
run "release_health_and_roles" {
  command = apply
  assert {
    condition     = aws_lb_target_group.app.health_check[0].path == "/healthz" && aws_ecs_service.app["api"].deployment_circuit_breaker[0].rollback && aws_ecs_service.app["api"].deployment_minimum_healthy_percent == 100 && aws_ecs_service.app["api"].deployment_maximum_percent == 200
    error_message = "Shallow health and explicit safe rollout required."
  }
  assert {
    condition     = aws_ecs_task_definition.app["worker"].task_role_arn != aws_ecs_task_definition.app["api"].task_role_arn && aws_appautoscaling_target.api.max_capacity == 8
    error_message = "API scaling and worker role must be independent."
  }
}

run "brevo_key_only_in_worker" {
  command = apply
  variables {
    runtime_secrets = {
      DATABASE_URL  = "arn:aws:ssm:us-east-1:123456789012:parameter/labseat/lab/DATABASE_URL"
      BREVO_API_KEY = "arn:aws:ssm:us-east-1:123456789012:parameter/labseat/lab/BREVO_API_KEY"
    }
  }
  assert {
    condition     = contains([for s in jsondecode(aws_ecs_task_definition.app["worker"].container_definitions)[0].secrets : s.name], "BREVO_API_KEY") && !contains([for s in jsondecode(aws_ecs_task_definition.app["api"].container_definitions)[0].secrets : s.name], "BREVO_API_KEY") && !contains([for s in jsondecode(aws_ecs_task_definition.app["publisher"].container_definitions)[0].secrets : s.name], "BREVO_API_KEY")
    error_message = "Only the notification worker receives the Brevo API secret."
  }
}
