locals {
  name = "${var.project}-${var.environment}"
  tags = { Project = var.project, Environment = var.environment, Owner = "tv1", ManagedBy = "Terraform" }
  subnets = {
    public_a = { az = var.availability_zones[0], tier = "public", cidr = cidrsubnet(var.vpc_cidr, 8, 0) }
    public_b = { az = var.availability_zones[1], tier = "public", cidr = cidrsubnet(var.vpc_cidr, 8, 1) }
    app_a    = { az = var.availability_zones[0], tier = "app", cidr = cidrsubnet(var.vpc_cidr, 8, 10) }
    app_b    = { az = var.availability_zones[1], tier = "app", cidr = cidrsubnet(var.vpc_cidr, 8, 11) }
    db_a     = { az = var.availability_zones[0], tier = "db", cidr = cidrsubnet(var.vpc_cidr, 8, 20) }
    db_b     = { az = var.availability_zones[1], tier = "db", cidr = cidrsubnet(var.vpc_cidr, 8, 21) }
  }
}
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = "${local.name}-vpc" })
}
resource "aws_subnet" "this" {
  for_each                = local.subnets
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = false
  tags                    = merge(local.tags, { Name = "${local.name}-${each.key}", Tier = each.value.tier })
}
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${local.name}-igw" })
}
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = merge(local.tags, { Name = "${local.name}-nat-eip" })
}
resource "aws_nat_gateway" "this" {
  allocation_id     = aws_eip.nat.id
  subnet_id         = aws_subnet.this["public_a"].id
  connectivity_type = "public"
  depends_on        = [aws_internet_gateway.this]
  tags              = merge(local.tags, { Name = "${local.name}-nat" })
}
resource "aws_route_table" "tier" {
  for_each = toset(["public", "app", "db"])
  vpc_id   = aws_vpc.this.id
  tags     = merge(local.tags, { Name = "${local.name}-${each.key}-rt" })
}
resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.tier["public"].id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}
resource "aws_route" "app_default" {
  route_table_id         = aws_route_table.tier["app"].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this.id
}
# DB table intentionally has no Internet default route or endpoint association.
resource "aws_route_table_association" "this" {
  for_each       = local.subnets
  subnet_id      = aws_subnet.this[each.key].id
  route_table_id = aws_route_table.tier[each.value.tier].id
}
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.tier["app"].id]
  tags              = merge(local.tags, { Name = "${local.name}-s3" })
}
