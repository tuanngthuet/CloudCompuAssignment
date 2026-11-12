provider "aws" {
  region              = var.region
  allowed_account_ids = [var.expected_account_id]
}
module "network" {
  source             = "../../modules/network"
  project            = var.project
  environment        = var.environment
  region             = var.region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
}
