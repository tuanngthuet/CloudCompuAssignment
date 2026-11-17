variable "project" {
  description = "Lowercase project slug used in resource names."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9]*(-[a-z0-9]+)*$", var.project)) && length(var.project) <= 20
    error_message = "Use a lowercase slug starting with a letter, up to 20 characters."
  }
}

variable "environment" {
  description = "Lowercase environment slug used in resource names."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9]*(-[a-z0-9]+)*$", var.environment)) && length(var.environment) <= 11
    error_message = "Use a lowercase slug starting with a letter, up to 11 characters."
  }
}

variable "db_subnet_ids" {
  description = "At least two private DB subnet IDs in distinct AZs, supplied by the network owner."
  type        = set(string)

  validation {
    condition     = length(var.db_subnet_ids) >= 2 && alltrue([for id in var.db_subnet_ids : can(regex("^subnet-[a-f0-9]+$", id))])
    error_message = "Supply at least two distinct subnet IDs."
  }
}

variable "db_sg_id" {
  description = "DB security group allowing TCP 5432 from the API task security group."
  type        = string

  validation {
    condition     = can(regex("^sg-[a-f0-9]+$", var.db_sg_id))
    error_message = "Supply a security group ID."
  }
}

variable "db_name" {
  description = "Name of the initial PostgreSQL database."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.db_name))
    error_message = "Use 1 to 63 lowercase letters, digits or underscores, starting with a letter."
  }
}

variable "deletion_protection" {
  description = "Protect the primary DB until the team approves cleanup."
  type        = bool
  default     = true
}

variable "final_snapshot_identifier" {
  description = "Unique identifier for the final snapshot, chosen before approved cleanup."
  type        = string
  default     = null
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "backup_retention_days" {
  description = "Automated backup retention; keep backups enabled even on restricted account plans."
  type        = number
  default     = 30
  validation {
    condition     = var.backup_retention_days >= 1 && var.backup_retention_days <= 35 && floor(var.backup_retention_days) == var.backup_retention_days
    error_message = "Keep automated backups enabled with 1 to 35 whole days of retention."
  }
}
