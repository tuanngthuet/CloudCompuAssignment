variable "alb_arn_suffix" {
  description = "Application Load Balancer ARN suffix from the compute module."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^app/[A-Za-z0-9-]+/[a-f0-9]+$", var.alb_arn_suffix))
    error_message = "alb_arn_suffix must have the format app/load-balancer-name/hex-id."
  }
}

variable "target_group_arn_suffix" {
  description = "Application target group ARN suffix from the compute module."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^targetgroup/[A-Za-z0-9-]+/[a-f0-9]+$", var.target_group_arn_suffix))
    error_message = "target_group_arn_suffix must have the format targetgroup/target-group-name/hex-id."
  }
}

variable "asg_name" {
  description = "Name of the application Auto Scaling group from the compute module."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.asg_name)) > 0
    error_message = "asg_name must be a non-empty Auto Scaling group name."
  }
}

variable "db_instance_identifier" {
  description = "RDS DB instance identifier from the data module, used for CloudWatch metrics."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.db_instance_identifier)) > 0
    error_message = "db_instance_identifier must be a non-empty DB instance identifier."
  }
}

variable "alarm_email" {
  description = "Email address for the workload alarm. The recipient confirms the SNS subscription."
  type        = string
  nullable    = false
  sensitive   = true

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.alarm_email))
    error_message = "alarm_email must be a valid email address."
  }
}

variable "environment" {
  description = "LabSeat environment name, shared with compute and IAM for the application log group."
  type        = string
  default     = "lab"
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,10}[a-z0-9])?$", var.environment))
    error_message = "environment must contain 1 to 12 lowercase letters, digits or hyphens and start and end with a letter or digit."
  }
}

variable "scaling_target_requests_per_target" {
  description = "Target tracking request count per healthy target per minute. Tune after measuring with k6."
  type        = number
  default     = 300
  nullable    = false

  validation {
    condition     = var.scaling_target_requests_per_target > 0
    error_message = "scaling_target_requests_per_target must be greater than zero."
  }
}
