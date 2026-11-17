variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Supply the verified AWS account ID."
  }
}
variable "network" {
  description = "Reviewed outputs from bootstrap/network-stack; never create a second VPC."
  type = object({
    vpc_id            = string
    public_subnet_ids = set(string)
    app_subnet_ids    = set(string)
    db_subnet_ids     = set(string)
    alb_sg_id         = string
    app_sg_id         = string
    db_sg_id          = string
    redis_sg_id       = optional(string)
  })
}
variable "redis_ami_id" {
  type    = string
  default = null
}
variable "cache_compatibility_verified" {
  type    = bool
  default = false
}
variable "alarm_email" {
  type      = string
  sensitive = true
}
variable "kms_key_arn" {
  type    = string
  default = null
}
variable "redis_enabled" {
  type    = bool
  default = false
}
variable "s3_image_prefix" {
  description = "Image object prefix matching the runtime S3_PREFIX; application images are stored in ECR."
  type        = string
  default     = ""
  nullable    = false
  validation {
    condition     = var.s3_image_prefix == "" || (can(regex("^[A-Za-z0-9_-][A-Za-z0-9._/-]*$", var.s3_image_prefix)) && !strcontains(var.s3_image_prefix, "..") && !strcontains(var.s3_image_prefix, "//"))
    error_message = "Use an empty prefix or a relative object path without wildcards, whitespace or parent segments."
  }
}

variable "capacity" {
  type    = object({ min = number, desired = number, max = number })
  default = { min = 2, desired = 2, max = 6 }
}
variable "instance_type" {
  type    = string
  default = "t3.small"
}
variable "db_pool_size" {
  type    = number
  default = 3
}
variable "db_connection_budget" {
  type    = number
  default = 66
}
variable "db_reserved_connections" {
  type    = number
  default = 12
}
variable "acm_certificate_arn" {
  type    = string
  default = null
}
variable "allow_http_demo" {
  type    = bool
  default = false
}
variable "scaling_target_requests_per_target" {
  type    = number
  default = 660
}
variable "workload_threshold" {
  type    = number
  default = 660
}

variable "region" { default = "us-east-1" }
variable "image" {
  description = "Immutable ECR image digest or unique release tag. Repository is created before first push."
  type        = string
  validation {
    condition     = can(regex("@sha256:[a-f0-9]{64}$", var.image))
    error_message = "Pin the bootstrap/release image by sha256 digest; never latest."
  }
}
variable "production" { default = false }
variable "managed_redis" { default = false }
variable "redis_auth_token" {
  type      = string
  sensitive = true
  default   = null
}
variable "email_backend" {
  default = "disabled"
  validation {
    condition     = contains(["disabled", "brevo"], var.email_backend)
    error_message = "Use disabled or brevo."
  }
}
variable "api_tasks" {
  type    = object({ min = number, max = number })
  default = { min = 2, max = 8 }
}
resource "terraform_data" "profile_guard" {
  lifecycle {
    precondition {
      condition     = var.email_backend != "brevo" || (can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.brevo_from_email)) && startswith(var.email_public_base_url, "https://"))
      error_message = "Brevo requires a verified sender email and public HTTPS LABSEAT URL."
    }
    precondition {
      condition     = !var.realtime_enabled || var.redis_enabled
      error_message = "Realtime requires a Redis endpoint with its separate Pub/Sub ACL."
    }
    precondition {
      condition     = !var.realtime_enabled || !var.managed_redis || var.redis_events_password != null
      error_message = "Managed realtime requires a separate events password."
    }
    precondition {
      condition     = !var.production || (var.managed_redis && var.redis_enabled)
      error_message = "Production requires managed replicated Redis."
    }
  }
}
variable "bootstrap" {
  type    = bool
  default = false
}

variable "redis_operator_password" {
  type      = string
  sensitive = true
  default   = null
}

variable "target_capacity" {
  type    = number
  default = 80
}

variable "brevo_from_email" {
  type    = string
  default = ""
}
variable "brevo_from_name" {
  type    = string
  default = "LABSEAT"
}
variable "email_public_base_url" {
  type    = string
  default = ""
}
variable "email_support_email" {
  type    = string
  default = ""
}

variable "maintenance_enabled" {
  type    = bool
  default = true
}
variable "realtime_enabled" {
  type    = bool
  default = false
}
variable "redis_events_password" {
  type      = string
  sensitive = true
  default   = null
}

variable "db_backup_retention_days" {
  description = "RDS automated backup retention; defaults to 30 days."
  type        = number
  default     = 30
}
