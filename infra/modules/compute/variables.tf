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

variable "ami_id" {
  description = "Available x86_64, HVM, EBS-backed LabSeat application AMI in the AWS provider region."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^ami-([0-9a-f]{8}|[0-9a-f]{17})$", var.ami_id))
    error_message = "ami_id must be an EC2 AMI ID."
  }
}
