variable "app_bucket_arn" {
  description = "The app bucket ARN without a trailing slash or object prefix."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]+$", var.app_bucket_arn))
    error_message = "Supply a bucket ARN without a prefix or wildcard."
  }
}

variable "parameter_prefix_arn" {
  description = "Parameter Store path ARN ending in parameter/labseat/lab/ without a wildcard."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:ssm:[a-z0-9-]+:[0-9]{12}:parameter/labseat/lab/$", var.parameter_prefix_arn))
    error_message = "Supply a Parameter Store path ARN ending in parameter/labseat/lab/."
  }
}

variable "kms_key_arn" {
  description = "Optional customer-managed key ARN for the app's SecureString parameters."
  type        = string
  default     = null

  validation {
    condition     = var.kms_key_arn == null || can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/[a-zA-Z0-9-]+$", var.kms_key_arn))
    error_message = "Supply a KMS key ARN or null."
  }
}

variable "log_group_arns" {
  description = "Precreated app log group ARNs, with or without the AWS :* suffix."
  type        = set(string)

  validation {
    condition = alltrue([
      for arn in var.log_group_arns : can(regex("^arn:aws[a-z-]*:logs:[a-z0-9-]+:[0-9]{12}:log-group:[A-Za-z0-9_./#-]+(:[*])?$", arn))
    ])
    error_message = "Supply exact log group ARNs, optionally ending in :*."
  }
}

variable "redis_enabled" {
  type    = bool
  default = false
}
variable "redis_parameter_prefix_arn" {
  description = "Cache-only path for CA, cert, private key and ACL file; never app runtime credentials."
  type        = string
  default     = null
  validation {
    condition     = var.redis_parameter_prefix_arn == null || can(regex("^arn:aws[a-z-]*:ssm:[a-z0-9-]+:[0-9]{12}:parameter/labseat/lab/cache/$", var.redis_parameter_prefix_arn))
    error_message = "Use parameter/labseat/lab/cache/ for cache bootstrap."
  }
}

variable "redis_log_group_arns" {
  description = "Precreated cache-only log group ARNs; not granted to app profiles."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for arn in var.redis_log_group_arns : can(regex("^arn:aws[a-z-]*:logs:[a-z0-9-]+:[0-9]{12}:log-group:[A-Za-z0-9_./#-]+(:[*])?$", arn))])
    error_message = "Supply exact cache log group ARNs."
  }
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
