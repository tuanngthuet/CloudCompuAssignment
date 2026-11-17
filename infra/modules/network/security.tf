resource "aws_security_group" "tier" {
  for_each    = toset(concat(["alb", "app", "db"], var.redis_enabled ? ["redis"] : []))
  name        = "${local.name}-${each.key}"
  description = "LabSeat ${each.key} tier, managed by Terraform"
  vpc_id      = aws_vpc.this.id
  tags        = merge(local.tags, { Name = "${local.name}-${each.key}-sg" })
}
resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.tier["alb"].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "HTTP lab demo with synthetic data only"
}
resource "aws_vpc_security_group_egress_rule" "alb_to_app" {
  security_group_id            = aws_security_group.tier["alb"].id
  referenced_security_group_id = aws_security_group.tier["app"].id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
  description                  = "Application traffic and health checks"
}
resource "aws_vpc_security_group_ingress_rule" "app_from_alb" {
  security_group_id            = aws_security_group.tier["app"].id
  referenced_security_group_id = aws_security_group.tier["alb"].id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}
resource "aws_vpc_security_group_egress_rule" "app_to_db" {
  security_group_id            = aws_security_group.tier["app"].id
  referenced_security_group_id = aws_security_group.tier["db"].id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
resource "aws_vpc_security_group_ingress_rule" "db_from_app" {
  security_group_id            = aws_security_group.tier["db"].id
  referenced_security_group_id = aws_security_group.tier["app"].id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
resource "aws_vpc_security_group_egress_rule" "app_web" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.tier["app"].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.key)
  to_port           = tonumber(each.key)
  description       = "OS repositories, SSM, CloudWatch, Parameter Store and HTTPS services"
}
# No inbound SSH. DB has no explicit outbound rule; replies are stateful.
# Amazon-provided DNS is not blocked by SG rules.

resource "aws_vpc_security_group_ingress_rule" "redis_from_app" {
  for_each                     = var.redis_enabled ? toset(["app"]) : toset([])
  security_group_id            = aws_security_group.tier["redis"].id
  referenced_security_group_id = aws_security_group.tier[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}
resource "aws_vpc_security_group_egress_rule" "app_to_redis" {
  for_each                     = var.redis_enabled ? toset(["app"]) : toset([])
  security_group_id            = aws_security_group.tier[each.key].id
  referenced_security_group_id = aws_security_group.tier["redis"].id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}
resource "aws_vpc_security_group_egress_rule" "extension_https" {
  for_each          = var.redis_enabled ? toset(["redis"]) : toset([])
  security_group_id = aws_security_group.tier[each.key].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "SSM, logs, Parameter Store and HTTPS package sources via NAT"
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.tier["alb"].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
