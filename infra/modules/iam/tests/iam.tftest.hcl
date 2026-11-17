mock_provider "aws" {}
variables {
  queue_arn                  = "arn:aws:sqs:us-east-1:123456789012:notifications"
  app_bucket_arn             = "arn:aws:s3:::labseat-fixture-bucket"
  parameter_prefix_arn       = "arn:aws:ssm:us-east-1:123456789012:parameter/labseat/lab/"
  log_group_arns             = ["arn:aws:logs:us-east-1:123456789012:log-group:/labseat/lab/app"]
  redis_log_group_arns       = ["arn:aws:logs:us-east-1:123456789012:log-group:/labseat/lab/redis"]
  redis_parameter_prefix_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/labseat/lab/cache/"
  redis_enabled              = true
}
run "least_privilege" {
  command = apply
  assert {
    condition     = !strcontains(aws_iam_role_policy.runtime.policy, "operator/") && !strcontains(aws_iam_role_policy.runtime.policy, "cache/") && strcontains(aws_iam_role_policy.secrets.policy, "REDIS_PASSWORD") && !strcontains(aws_iam_role_policy.runtime.policy, "/lab/redis")
    error_message = "App must not read operator or cache private keys."
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.redis[0].policy, "DATABASE_URL") && !strcontains(aws_iam_role_policy.redis[0].policy, "s3:") && strcontains(aws_iam_role_policy.redis[0].policy, "cache/SERVER_KEY") && !strcontains(aws_iam_role_policy.redis[0].policy, "/lab/app")
    error_message = "Cache profile must not read app database or S3 data."
  }

}

run "event_and_room_images" {
  command = apply
  assert {
    condition = toset(jsondecode(aws_iam_role_policy.api.policy).Statement[0].Resource) == toset([
      "arn:aws:s3:::labseat-fixture-bucket/rooms/*",
      "arn:aws:s3:::labseat-fixture-bucket/events/*",
      "arn:aws:s3:::labseat-fixture-bucket/users/*",
    ])
    error_message = "Only room and event images may be written; do not grant bucket-wide access."
  }

}

run "prefixed_event_images" {
  command = apply
  variables {
    s3_image_prefix = "labseat/media/"
  }
  assert {
    condition = toset(jsondecode(aws_iam_role_policy.api.policy).Statement[0].Resource) == toset([
      "arn:aws:s3:::labseat-fixture-bucket/labseat/media/rooms/*",
      "arn:aws:s3:::labseat-fixture-bucket/labseat/media/events/*",
      "arn:aws:s3:::labseat-fixture-bucket/labseat/media/users/*",
    ])
    error_message = "Image permissions must match S3_PREFIX."
  }

}

run "reject_wildcard_prefix" {
  command = plan
  variables {
    s3_image_prefix = "*"
  }
  expect_failures = [var.s3_image_prefix]
}

run "separate_task_permissions" {
  command = apply
  assert {
    condition     = !strcontains(aws_iam_role_policy.api.policy, "sqs:") && !strcontains(aws_iam_role_policy.worker.policy, "s3:") && !strcontains(aws_iam_role_policy.publisher.policy, "s3:") && jsondecode(aws_iam_role_policy.runtime.policy).Statement[0].Effect == "Deny"
    error_message = "Task roles have separate S3 and SQS responsibilities; host cannot read application data."
  }
}

run "brevo_secret_is_execution_only" {
  command = apply
  variables {
    brevo_enabled = true
  }
  assert {
    condition     = strcontains(aws_iam_role_policy.secrets.policy, "/lab/BREVO_API_KEY") && !strcontains(aws_iam_role_policy.api.policy, "BREVO_API_KEY")
    error_message = "Brevo key is injected by execution role, without API task permissions."
  }
}
