variable "project" {
  description = "Project slug used in resource names and tags."
  type        = string
  default     = "labseat"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?$", var.project))
    error_message = "project must be a lowercase alphanumeric slug of at most 12 characters, with optional internal hyphens."
  }
}

variable "environment" {
  description = "Environment slug used in resource names and tags. The W1 AMI reads configuration for lab."
  type        = string
  default     = "lab"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?$", var.environment))
    error_message = "environment must be a lowercase alphanumeric slug of at most 12 characters, with optional internal hyphens."
  }
}

variable "vpc_id" {
  description = "ID of the VPC supplied by the network owner."
  type        = string
  nullable    = false
}

variable "public_subnet_ids" {
  description = "Two public subnets in different availability zones for the internet-facing ALB."
  type        = set(string)
  nullable    = false

  validation {
    condition     = length(var.public_subnet_ids) == 2
    error_message = "Provide two distinct public subnet IDs."
  }
}

variable "app_subnet_ids" {
  description = "Two private app subnets in the same availability zones as the ALB."
  type        = set(string)
  nullable    = false

  validation {
    condition     = length(var.app_subnet_ids) == 2
    error_message = "Provide two distinct private app subnet IDs."
  }
}

variable "alb_sg_id" {
  description = "Security group ID for the ALB supplied by the network owner."
  type        = string
  nullable    = false
}

variable "app_sg_id" {
  description = "Security group ID for the app instances supplied by the network owner."
  type        = string
  nullable    = false
}

variable "app_instance_profile_name" {
  description = "Name of the existing EC2 runtime instance profile supplied by the IAM owner."
  type        = string
  nullable    = false
}

variable "capacity" {
  type    = object({ min = number, desired = number, max = number })
  default = { min = 2, desired = 2, max = 6 }
  validation {
    condition     = var.capacity.min >= 2 && var.capacity.min <= var.capacity.desired && var.capacity.desired <= var.capacity.max && alltrue([for n in values(var.capacity) : n == floor(n)])
    error_message = "Use ordered integer capacity min>=2, desired>=min, max>=desired."
  }
}
variable "instance_type" {
  type    = string
  default = "t3.small"
}
variable "db_pool_size" {
  type    = number
  default = 3
  validation {
    condition     = var.db_pool_size >= 1 && var.db_pool_size <= 3 && var.db_pool_size == floor(var.db_pool_size)
    error_message = "Use a bounded integer pool1..3 per single worker."
  }
}
variable "db_connection_budget" {
  type    = number
  default = 66
  validation {
    condition     = var.db_connection_budget >= 1 && var.db_connection_budget == floor(var.db_connection_budget)
    error_message = "Supply the reviewed positive integer database connection budget."
  }
}
variable "db_reserved_connections" {
  type    = number
  default = 12
  validation {
    condition     = var.db_reserved_connections >= 1 && var.db_reserved_connections == floor(var.db_reserved_connections)
    error_message = "Reserve a positive integer number of database connections outside app pools."
  }
}
variable "redis_enabled" {
  type    = bool
  default = false
}
variable "acm_certificate_arn" {
  type    = string
  default = null
}
variable "allow_http_demo" {
  type    = bool
  default = false
}

variable "image" { type = string }
variable "execution_role_arn" { type = string }
variable "app_role_arn" { type = string }
variable "worker_role_arn" { type = string }
variable "publisher_role_arn" { type = string }
variable "log_group" { type = string }
variable "region" { type = string }
variable "runtime_secrets" { type = map(string) }
variable "runtime_environment" { type = map(string) }
variable "background_pool_size" { default = 1 }
variable "api_tasks" {
  type    = object({ min = number, max = number })
  default = { min = 2, max = 8 }
  validation {
    condition     = var.api_tasks.min >= 2 && var.api_tasks.max >= var.api_tasks.min && alltrue([for n in values(var.api_tasks) : n == floor(n)])
    error_message = "API task bounds must be integers, min >=2 and max >=min."
  }
}
variable "target_capacity" {
  default = 80
  validation {
    condition     = var.target_capacity >= 1 && var.target_capacity <= 100
    error_message = "Target capacity must be 1..100."
  }
}
variable "deployment_maximum_percent" {
  default = 200
  validation {
    condition     = var.deployment_maximum_percent == 200
    error_message = "This profile reserves 100/200 rolling deployment headroom."
  }
}
variable "requests_per_target" { default = 300 }

variable "bootstrap" {
  type    = bool
  default = false
}
