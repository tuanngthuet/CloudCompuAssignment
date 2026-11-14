locals {
  log_groups = [for arn in var.log_group_arns : trimsuffix(arn, ":*")]
  log_streams = [
    for arn in local.log_groups : "${arn}:log-stream:*"
  ]
  parameter_arn    = "${var.parameter_prefix_arn}*"
  parameter_region = split(":", var.parameter_prefix_arn)[3]
  dns_suffix       = startswith(local.parameter_region, "cn-") ? "amazonaws.com.cn" : "amazonaws.com"
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

resource "aws_iam_role_policy" "runtime" {
  name = "labseat-runtime"
  role = aws_iam_role.app.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid      = "ListAppPrefixes"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = var.app_bucket_arn
        Condition = {
          StringLike = { "s3:prefix" = ["rooms/*", "releases/*"] }
        }
      },
      {
        Sid      = "ReadAndWriteRoomImages"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${var.app_bucket_arn}/rooms/*"
      },
      {
        Sid      = "ReadReleaseObjects"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${var.app_bucket_arn}/releases/*"
      },
      {
        Sid      = "ReadAppParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = local.parameter_arn
      },
      {
        Sid    = "SSMAgentSessionChannels"
        Effect = "Allow"
        Action = [
          "ssm:UpdateInstanceInformation",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      }
      ], [for arn in local.log_groups : {
        Effect   = "Allow"
        Action   = "logs:DescribeLogStreams"
        Resource = arn
        }], [for arn in local.log_streams : {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = arn
        }], [for key_arn in var.kms_key_arn[*] : {
        Sid      = "DecryptAppParameters"
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = key_arn
        Condition = {
          StringEquals = { "kms:ViaService" = "ssm.${local.parameter_region}.${local.dns_suffix}" }
          StringLike   = { "kms:EncryptionContext:PARAMETER_ARN" = local.parameter_arn }
        }
      }]
    )
  })
}

resource "aws_iam_instance_profile" "app" {
  name_prefix = "labseat-app-"
  role        = aws_iam_role.app.name
}
