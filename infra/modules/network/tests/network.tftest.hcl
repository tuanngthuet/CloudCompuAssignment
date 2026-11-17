mock_provider "aws" {}
run "network_contract" {
  command = apply
  assert {
    condition     = length(aws_subnet.this) == 6 && length(distinct([for s in aws_subnet.this : s.availability_zone])) == 2
    error_message = "Must create exactly six subnets across two AZs."
  }
  assert {
    condition     = alltrue([for s in aws_subnet.this : !s.map_public_ip_on_launch])
    error_message = "Subnet auto-assignment of public IPs must remain disabled."
  }
  assert {
    condition     = aws_nat_gateway.this.subnet_id == aws_subnet.this["public_a"].id && aws_route.app_default.nat_gateway_id == aws_nat_gateway.this.id
    error_message = "App traffic must use the single NAT in public_a."
  }
  assert {
    condition     = aws_route.public_default.gateway_id == aws_internet_gateway.this.id && aws_route.public_default.route_table_id == aws_route_table.tier["public"].id
    error_message = "Public default route must use IGW."
  }
  assert {
    condition     = aws_route_table_association.this["db_a"].route_table_id == aws_route_table.tier["db"].id && aws_route_table_association.this["db_b"].route_table_id == aws_route_table.tier["db"].id && !contains([aws_route.public_default.route_table_id, aws_route.app_default.route_table_id], aws_route_table.tier["db"].id)
    error_message = "DB subnets must use a separate route table without declared default route."
  }
  assert {
    condition     = toset(aws_vpc_endpoint.s3.route_table_ids) == toset([aws_route_table.tier["app"].id])
    error_message = "S3 endpoint must serve app tier only."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.app_from_alb.referenced_security_group_id == output.alb_sg_id && aws_vpc_security_group_ingress_rule.app_from_alb.from_port == 8000 && aws_vpc_security_group_ingress_rule.db_from_app.referenced_security_group_id == output.app_sg_id && aws_vpc_security_group_ingress_rule.db_from_app.from_port == 5432
    error_message = "App/DB ingress must follow ALB -> app:8000 -> DB:5432."
  }
  assert {
    condition     = length(output.public_subnet_ids) == 2 && length(output.app_subnet_ids) == 2 && length(output.db_subnet_ids) == 2
    error_message = "Contract output subnet lists must each contain two IDs."
  }
}
run "reject_duplicate_az" {
  command = plan
  variables { availability_zones = ["us-east-1a", "us-east-1a"] }
  expect_failures = [var.availability_zones]
}
run "reject_other_region" {
  command = plan
  variables { region = "eu-west-1" }
  expect_failures = [var.region]
}
run "reject_small_cidr" {
  command = plan
  variables { vpc_cidr = "10.20.0.0/24" }
  expect_failures = [var.vpc_cidr]
}
run "optional_redis_private_paths" {
  command = apply
  variables { redis_enabled = true }
  assert {
    condition     = length(aws_security_group.tier) == 4 && output.app_sg_id == run.network_contract.app_sg_id
    error_message = "Optional Redis adds one SG and retains the application SG address."
  }
  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.redis_from_app) == 1 && aws_vpc_security_group_ingress_rule.redis_from_app["app"].from_port == 6379 && aws_vpc_security_group_ingress_rule.redis_from_app["app"].cidr_ipv4 == null
    error_message = "Redis accepts only the application SG on TLS6379."
  }
}

run "production_nat_per_az" {
  command = apply
  variables { multi_az_nat = true }
  assert {
    condition     = length(aws_nat_gateway.b) == 1 && aws_route_table_association.this["app_b"].route_table_id == aws_route_table.app_b[0].id && length(aws_vpc_endpoint.s3.route_table_ids) == 2
    error_message = "Production private subnets need independent per-AZ outbound routes and S3 endpoint associations."
  }
}

run "sydney_production_network" {
  command = apply
  variables {
    region             = "ap-southeast-2"
    availability_zones = ["ap-southeast-2a", "ap-southeast-2b"]
    multi_az_nat       = true
  }
  assert {
    condition     = alltrue([for subnet in aws_subnet.this : startswith(subnet.availability_zone, "ap-southeast-2")]) && aws_vpc_endpoint.s3.service_name == "com.amazonaws.ap-southeast-2.s3" && length(aws_nat_gateway.b) == 1
    error_message = "Sydney production must use local AZs, the regional S3 endpoint and two NAT gateways."
  }
}
run "reject_az_from_other_region" {
  command = plan
  variables {
    region             = "ap-southeast-2"
    availability_zones = ["us-east-1a", "us-east-1b"]
  }
  expect_failures = [var.availability_zones]
}
