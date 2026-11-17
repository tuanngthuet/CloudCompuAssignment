output "alb_url" { value = module.compute.alb_url }
output "redis_endpoint" { value = var.managed_redis ? try(module.managed_cache[0].endpoint, null) : try(module.cache[0].redis_endpoint, null) }
output "redis_instance_id" { value = try(module.cache[0].redis_instance_id, null) }
output "db_endpoint" { value = module.data.db_endpoint }
output "s3_bucket" { value = module.data.app_bucket_name }
output "asg_name" { value = module.compute.asg_name }
output "target_group_arn" { value = module.compute.target_group_arn }
output "launch_template_id" { value = module.compute.launch_template_id }
output "launch_template_version" { value = module.compute.launch_template_version }

output "cluster_name" { value = module.compute.cluster_name }
output "capacity_provider" { value = module.compute.capacity_provider }
output "repository_url" { value = module.compute.repository_url }
output "services" { value = module.compute.services }
output "task_definitions" { value = module.compute.task_definitions }
output "queue_url" { value = module.messaging.queue_url }
output "deployment" {
  value = {
    maintenance       = var.maintenance_enabled ? { task_definition = module.compute.maintenance_task_definition, schedule = module.compute.maintenance_schedule } : null
    cluster           = module.compute.cluster_name
    api_tasks         = var.api_tasks
    capacity_provider = module.compute.capacity_provider
    services          = module.compute.services
    task_definitions  = module.compute.task_definitions
    subnets           = var.network.app_subnet_ids
    security_groups   = [var.network.app_sg_id]
    repository        = module.compute.repository_url
    region            = var.region
    account           = var.expected_account_id
    alb_url           = module.compute.alb_url
  }
}
