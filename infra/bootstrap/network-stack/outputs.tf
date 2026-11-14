output "vpc_id" {
  value = module.network.vpc_id
}
output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}
output "app_subnet_ids" {
  value = module.network.app_subnet_ids
}
output "db_subnet_ids" {
  value = module.network.db_subnet_ids
}
output "alb_sg_id" {
  value = module.network.alb_sg_id
}
output "app_sg_id" {
  value = module.network.app_sg_id
}
output "db_sg_id" {
  value = module.network.db_sg_id
}
output "s3_endpoint_id" {
  value = module.network.s3_endpoint_id
}
