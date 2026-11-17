variable "project" {
  type    = string
  default = "labseat"
}
variable "environment" {
  type    = string
  default = "lab"
}
variable "region" {
  type    = string
  default = "us-east-1"
  validation {
    condition     = contains(["us-east-1", "ap-southeast-2"], var.region)
    error_message = "Use a supported LABSEAT region: us-east-1 or ap-southeast-2."
  }
}
variable "app_subnet_id" { type = string }
variable "redis_sg_id" { type = string }
variable "redis_instance_profile_name" { type = string }
variable "redis_ami_id" {
  description = "Private cache AMI built with scripts/cache/redis.pkr.hcl; never the app AMI."
  type        = string
  validation {
    condition     = can(regex("^ami-([0-9a-f]{8}|[0-9a-f]{17})$", var.redis_ami_id))
    error_message = "Supply the verified cache AMI ID."
  }
}
variable "redis_engine_version" {
  type    = string
  default = "7.4.12"
  validation {
    condition     = var.redis_engine_version == "7.4.12"
    error_message = "The supplied cache builder is pinned to Redis 7.4.12; revalidate before updating."
  }
}
variable "compatibility_verified" {
  description = "Operator confirms the pinned candidate compatibility evidence; not an AWS acceptance claim."
  type        = bool
  default     = false
}
variable "parameter_prefix" {
  type    = string
  default = "/labseat/lab/cache/"
  validation {
    condition     = var.parameter_prefix == "/labseat/lab/cache/"
    error_message = "Cache bootstrap is restricted to /labseat/lab/cache/."
  }
}
