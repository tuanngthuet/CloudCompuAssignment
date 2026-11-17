variable "name" { type = string }
variable "subnet_ids" { type = set(string) }
variable "security_group_id" { type = string }
variable "high_availability" { type = bool }
variable "auth_token" {
  type      = string
  sensitive = true
  nullable  = false
}
resource "aws_elasticache_subnet_group" "app" {
  name       = var.name
  subnet_ids = var.subnet_ids
}
resource "aws_elasticache_replication_group" "app" {
  replication_group_id       = var.name
  description                = "LABSEAT admission only; PostgreSQL owns reservations"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t3.micro"
  port                       = 6379
  parameter_group_name       = aws_elasticache_parameter_group.app.name
  num_cache_clusters         = var.high_availability ? 2 : 1
  automatic_failover_enabled = var.high_availability
  multi_az_enabled           = var.high_availability
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  user_group_ids             = [aws_elasticache_user_group.app.id]
  subnet_group_name          = aws_elasticache_subnet_group.app.name
  security_group_ids         = [var.security_group_id]
  snapshot_retention_limit   = var.high_availability ? 7 : 1
}
output "endpoint" { value = aws_elasticache_replication_group.app.primary_endpoint_address }

resource "aws_elasticache_parameter_group" "app" {
  name   = var.name
  family = "redis7"
  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }
}

variable "operator_password" {
  type      = string
  sensitive = true
  nullable  = false
}
locals {
  runtime_commands = "+ping +hello +info +evalsha +script|load +time +get +type +incr +zadd +zrem +zrange +zrangebyscore +zcount +zcard +zrank +hget +hset +hlen +hdel +expire +pexpire +pexpireat +exists +zscore +del"
}
resource "aws_elasticache_user" "disabled_default" {
  user_id              = "${var.name}-default"
  user_name            = "default"
  engine               = "redis"
  access_string        = "off -@all"
  no_password_required = true
}
resource "aws_elasticache_user" "runtime" {
  user_id       = "${var.name}-runtime"
  user_name     = "runtime"
  engine        = "redis"
  access_string = "on ~labseat:queue:* -@all ${local.runtime_commands}"
  passwords     = [var.auth_token]
}
resource "aws_elasticache_user" "operator" {
  user_id       = "${var.name}-operator"
  user_name     = "operator"
  engine        = "redis"
  access_string = "on ~labseat:queue:* -@all ${local.runtime_commands} +set +scan +unlink"
  passwords     = [var.operator_password]
}
resource "aws_elasticache_user_group" "app" {
  user_group_id = var.name
  engine        = "redis"
  user_ids      = concat([aws_elasticache_user.disabled_default.user_id, aws_elasticache_user.runtime.user_id, aws_elasticache_user.operator.user_id], aws_elasticache_user.events[*].user_id)
}

output "cluster_ids" { value = aws_elasticache_replication_group.app.member_clusters }

variable "events_password" {
  type      = string
  sensitive = true
  default   = null
}
resource "aws_elasticache_user" "events" {
  count         = var.realtime_enabled ? 1 : 0
  user_id       = "${var.name}-events"
  user_name     = "events"
  engine        = "redis"
  access_string = "on resetchannels &labseat:events:* -@all +ping +hello +publish +subscribe +unsubscribe"
  passwords     = [var.events_password]
}

variable "realtime_enabled" {
  type    = bool
  default = false
}
