provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id]
}
module "network" {
  source             = "../../modules/network"
  multi_az_nat       = var.multi_az_nat
  redis_enabled      = var.redis_enabled
  project            = var.project
  environment        = var.environment
  region             = var.region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}
