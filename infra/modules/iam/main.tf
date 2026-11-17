locals {
  image_prefix = var.s3_image_prefix == "" ? "" : "${trimsuffix(var.s3_image_prefix, "/")}/"
  image_paths  = [for directory in ["rooms", "events", "users"] : "${local.image_prefix}${directory}/*"]

  cache_log_groups  = [for arn in var.redis_log_group_arns : trimsuffix(arn, ":*")]
  cache_log_streams = [for arn in local.cache_log_groups : "${arn}:log-stream:*"]
  log_groups        = [for arn in var.log_group_arns : trimsuffix(arn, ":*")]
  log_streams = [
    for arn in local.log_groups : "${arn}:log-stream:*"
  ]
  app_parameter_names = concat(["DATABASE_URL", "AUTH_LINK_SIGNING_KEY", "BREVO_WEBHOOK_TOKEN"], var.realtime_enabled ? ["REDIS_EVENTS_URL", "REDIS_EVENTS_USERNAME", "REDIS_EVENTS_PASSWORD", "REDIS_CA_CERT"] : [], var.brevo_enabled ? ["BREVO_API_KEY"] : [], var.redis_enabled ? ["REDIS_URL", "REDIS_USERNAME", "REDIS_PASSWORD", "REDIS_CA_CERT"] : [])
  app_parameter_arns  = [for name in local.app_parameter_names : "${var.parameter_prefix_arn}${name}"]
  parameter_region    = split(":", var.parameter_prefix_arn)[3]
  dns_suffix          = startswith(local.parameter_region, "cn-") ? "amazonaws.com.cn" : "amazonaws.com"
}

resource "aws_iam_role" "app" {
  name_prefix = "labseat-app-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_instance" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}
resource "aws_iam_role_policy_attachment" "ssm_instance" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "runtime" {
  name   = "deny-container-instance-application-access"
  role   = aws_iam_role.app.name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Deny", Action = ["s3:*", "sqs:*", "ssm:GetParameter", "ssm:GetParameters", "secretsmanager:GetSecretValue"], Resource = "*" }] })
}

resource "aws_iam_instance_profile" "app" {
  name_prefix = "labseat-app-"
  role        = aws_iam_role.app.name
}

resource "aws_iam_role" "redis" {
  count              = var.redis_enabled ? 1 : 0
  name_prefix        = "labseat-redis-"
  assume_role_policy = aws_iam_role.app.assume_role_policy
}
resource "aws_iam_role_policy" "redis" {
  count = var.redis_enabled ? 1 : 0
  name  = "labseat-cache-runtime"
  role  = aws_iam_role.redis[0].name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameters"]
        Resource = [for name in ["CA_CERT", "SERVER_CERT", "SERVER_KEY", "ACL_FILE", "MONITOR_PASSWORD"] : "${var.redis_parameter_prefix_arn}${name}"]
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:UpdateInstanceInformation", "ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel"]
        Resource = "*"
      },
      {
        Effect    = "Allow"
        Action    = ["cloudwatch:PutMetricData"]
        Resource  = "*"
        Condition = { StringEquals = { "cloudwatch:namespace" = "LabSeat/Redis" } }
      }
      ], [for arn in local.cache_log_groups : {
        Effect   = "Allow"
        Action   = "logs:DescribeLogStreams"
        Resource = arn
        }], [for arn in local.cache_log_streams : {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = arn
        }], [for key in var.kms_key_arn[*] : {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = key
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${local.parameter_region}.${local.dns_suffix}" }
          StringLike   = { "kms:EncryptionContext:PARAMETER_ARN" = "${var.redis_parameter_prefix_arn}*" }
        }
    }])
  })
  lifecycle {
    precondition {
      condition     = var.redis_parameter_prefix_arn != null
      error_message = "Redis requires a cache-only Parameter Store prefix ARN."
    }
  }
}
resource "aws_iam_instance_profile" "redis" {
  count       = var.redis_enabled ? 1 : 0
  name_prefix = "labseat-redis-"
  role        = aws_iam_role.redis[0].name
}
