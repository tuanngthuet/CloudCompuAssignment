variable "queue_arn" { type = string }
locals {
  task_trust = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ecs-tasks.amazonaws.com" }, Condition = { StringEquals = { "aws:SourceAccount" = split(":", var.parameter_prefix_arn)[4] }, ArnLike = { "aws:SourceArn" = "arn:aws:ecs:${local.parameter_region}:${split(":", var.parameter_prefix_arn)[4]}:*" } } }] })
}
resource "aws_iam_role" "task" {
  for_each           = toset(["api", "worker", "publisher", "execution", "maintenance"])
  name_prefix        = "labseat-${each.key}-"
  assume_role_policy = local.task_trust
}
resource "aws_iam_role_policy" "api" {
  role = aws_iam_role.task["api"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
    Resource = [for path in local.image_paths : "${var.app_bucket_arn}/${path}"]
  }] })
}
resource "aws_iam_role_policy" "publisher" {
  role   = aws_iam_role.task["publisher"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sqs:SendMessage", Resource = var.queue_arn }] })
}
resource "aws_iam_role_policy" "worker" {
  role = aws_iam_role.task["worker"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = var.queue_arn }
  ] })
}
resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.task["execution"].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "secrets" {
  role = aws_iam_role.task["execution"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = "ssm:GetParameters", Resource = local.app_parameter_arns }
    ], [for key in var.kms_key_arn[*] : {
      Effect    = "Allow", Action = "kms:Decrypt", Resource = key,
      Condition = { StringEquals = { "kms:ViaService" = "ssm.${local.parameter_region}.${local.dns_suffix}" } }
  }]) })
}
output "task_roles" { value = { for k, r in aws_iam_role.task : k => r.arn } }

variable "brevo_enabled" {
  type    = bool
  default = false
}

variable "realtime_enabled" {
  type    = bool
  default = false
}
resource "aws_iam_role_policy" "maintenance" {
  role = aws_iam_role.task["maintenance"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "s3:ListBucket", Resource = var.app_bucket_arn, Condition = { StringLike = { "s3:prefix" = local.image_paths } } },
    { Effect = "Allow", Action = "s3:DeleteObject", Resource = [for path in local.image_paths : "${var.app_bucket_arn}/${path}"] }
  ] })
}
