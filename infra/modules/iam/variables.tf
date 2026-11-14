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
