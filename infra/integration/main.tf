# Network remains in the existing bootstrap/network-stack state. Pass its reviewed outputs.
provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id]
}
data "aws_partition" "current" {}
locals {
  parameter_prefix_arn = "arn:${data.aws_partition.current.partition}:ssm:${var.region}:${var.expected_account_id}:parameter/labseat/lab/"
}
module "data" {
  source                = "../modules/data"
  project               = "labseat"
  environment           = "lab"
  db_subnet_ids         = var.network.db_subnet_ids
  db_sg_id              = var.network.db_sg_id
  db_name               = "labseat"
  multi_az              = var.production
  backup_retention_days = var.db_backup_retention_days
}
module "iam" {
  source                     = "../modules/iam"
  app_bucket_arn             = module.data.app_bucket_arn
  queue_arn                  = module.messaging.queue_arn
  realtime_enabled           = var.realtime_enabled
  brevo_enabled              = var.email_backend == "brevo"
  s3_image_prefix            = var.s3_image_prefix
  parameter_prefix_arn       = local.parameter_prefix_arn
  redis_parameter_prefix_arn = "${local.parameter_prefix_arn}cache/"
  kms_key_arn                = var.kms_key_arn
  log_group_arns             = [module.observability.log_group_arn]
  redis_log_group_arns       = var.redis_enabled ? [module.observability.redis_log_group_arn] : []
  redis_enabled              = var.redis_enabled
}
module "compute" {
  requests_per_target       = var.scaling_target_requests_per_target
  target_capacity           = var.target_capacity
  bootstrap                 = var.bootstrap
  capacity                  = var.capacity
  instance_type             = var.instance_type
  db_pool_size              = var.db_pool_size
  db_connection_budget      = var.db_connection_budget
  db_reserved_connections   = var.db_reserved_connections
  acm_certificate_arn       = var.acm_certificate_arn
  allow_http_demo           = var.allow_http_demo
  source                    = "../modules/compute"
  vpc_id                    = var.network.vpc_id
  public_subnet_ids         = var.network.public_subnet_ids
  app_subnet_ids            = var.network.app_subnet_ids
  alb_sg_id                 = var.network.alb_sg_id
  app_sg_id                 = var.network.app_sg_id
  app_instance_profile_name = module.iam.app_instance_profile_name
  image                     = var.image
  execution_role_arn        = module.iam.task_roles["execution"]
  app_role_arn              = module.iam.task_roles["api"]
  worker_role_arn           = module.iam.task_roles["worker"]
  publisher_role_arn        = module.iam.task_roles["publisher"]
  maintenance_role_arn      = module.iam.task_roles["maintenance"]
  maintenance_enabled       = var.maintenance_enabled
  log_group                 = module.observability.log_group_name
  region                    = var.region
  api_tasks                 = var.api_tasks
  runtime_environment = {
    APP_ENV               = "production"
    FORWARDED_ALLOW_IPS   = "*"
    STORAGE_BACKEND       = "s3"
    S3_BUCKET             = module.data.app_bucket_name
    S3_PREFIX             = var.s3_image_prefix
    AWS_REGION            = var.region
    EMAIL_BACKEND         = var.email_backend
    BREVO_FROM_EMAIL      = var.brevo_from_email
    BREVO_FROM_NAME       = var.brevo_from_name
    EMAIL_PUBLIC_BASE_URL = var.email_public_base_url
    EMAIL_SUPPORT_EMAIL   = var.email_support_email
    SQS_QUEUE_URL         = module.messaging.queue_url
    REDIS_CA_PATH         = "/etc/ssl/certs/ca-certificates.crt"
  }
  runtime_secrets = { for name in distinct(concat(["DATABASE_URL", "AUTH_LINK_SIGNING_KEY", "BREVO_WEBHOOK_TOKEN"], var.realtime_enabled ? ["REDIS_EVENTS_URL", "REDIS_EVENTS_USERNAME", "REDIS_EVENTS_PASSWORD", "REDIS_CA_CERT"] : [], var.email_backend == "brevo" ? ["BREVO_API_KEY"] : [], var.redis_enabled ? ["REDIS_URL", "REDIS_USERNAME", "REDIS_PASSWORD", "REDIS_CA_CERT"] : [])) : name => "${local.parameter_prefix_arn}${name}" }
  redis_enabled   = var.redis_enabled
}
module "cache" {
  count                       = var.redis_enabled && !var.managed_redis ? 1 : 0
  source                      = "../modules/cache"
  region                      = var.region
  app_subnet_id               = sort(tolist(var.network.app_subnet_ids))[0]
  redis_sg_id                 = var.network.redis_sg_id
  redis_instance_profile_name = module.iam.redis_instance_profile_name
  redis_ami_id                = var.redis_ami_id
  compatibility_verified      = var.cache_compatibility_verified
}
module "observability" {
  maintenance_enabled                = var.maintenance_enabled
  db_connection_budget               = var.db_connection_budget
  managed_cache_clusters             = var.managed_redis && var.redis_enabled ? module.managed_cache[0].cluster_ids : []
  source                             = "../modules/observability"
  queue_name                         = module.messaging.queue_name
  dlq_name                           = module.messaging.dlq_name
  cluster_name                       = module.compute.cluster_name
  api_service_name                   = module.compute.services["api"]
  alb_arn_suffix                     = module.compute.alb_arn_suffix
  target_group_arn_suffix            = module.compute.target_group_arn_suffix
  asg_name                           = module.compute.asg_name
  db_instance_identifier             = module.data.db_instance_identifier
  redis_instance_id                  = var.redis_enabled && !var.managed_redis ? module.cache[0].redis_instance_id : null
  scaling_target_requests_per_target = var.scaling_target_requests_per_target
  workload_threshold                 = var.workload_threshold
  alarm_email                        = var.alarm_email
  redis_enabled                      = var.redis_enabled
}

module "messaging" {
  source = "../modules/messaging"
  name   = "labseat-lab"
}
module "managed_cache" {
  count             = var.redis_enabled && var.managed_redis ? 1 : 0
  source            = "../modules/managed_cache"
  name              = "labseat-lab"
  subnet_ids        = var.network.app_subnet_ids
  security_group_id = var.network.redis_sg_id
  high_availability = var.production
  auth_token        = var.redis_auth_token
  operator_password = var.redis_operator_password
  events_password   = var.redis_events_password
  realtime_enabled  = var.realtime_enabled
}
