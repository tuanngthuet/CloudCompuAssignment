variable "region" {
  type    = string
  default = "us-east-1"
  validation {
    condition     = contains(["us-east-1", "ap-southeast-2"], var.region)
    error_message = "Use a supported LABSEAT region: us-east-1 or ap-southeast-2."
  }
}
variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Use the real 12-digit AWS account ID."
  }
}
variable "state_bucket_name" {
  type        = string
  description = "Globally unique state-only bucket name; never reuse application bucket."
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "Use 3-63 lowercase letters, digits or hyphens."
  }
}
