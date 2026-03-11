# =============================================================================
# Accord TEE Negotiation Engine - Root Variables
# =============================================================================
# Input variables for the Accord GCP infrastructure.
# =============================================================================

variable "project_id" {
  description = "GCP project ID where all resources will be created."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Project ID must be 6-30 characters, start with a letter, and contain only lowercase letters, digits, and hyphens."
  }
}

variable "region" {
  description = "GCP region for resource deployment. Must support Confidential VMs with GPU."
  type        = string
  default     = "us-central1"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]$", var.region))
    error_message = "Region must be a valid GCP region identifier (e.g., us-central1)."
  }
}

variable "zone" {
  description = "GCP zone for zonal resources. Must be within the selected region and support g2 machine types."
  type        = string
  default     = "us-central1-a"

  validation {
    condition     = can(regex("^[a-z]+-[a-z]+[0-9]-[a-z]$", var.zone))
    error_message = "Zone must be a valid GCP zone identifier (e.g., us-central1-a)."
  }
}

variable "environment" {
  description = "Deployment environment name. Controls resource naming, sizing, and security posture."
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "domain" {
  description = "Domain name for the managed SSL certificate and Cloud DNS zone (e.g., accord.example.com)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.domain))
    error_message = "Domain must be a valid domain name."
  }
}

variable "alert_email" {
  description = "Email address for Cloud Monitoring alert notifications."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", var.alert_email))
    error_message = "Must be a valid email address."
  }
}

variable "machine_type" {
  description = "GCE machine type for Confidential VM instances. Must support GPUs and AMD SEV-SNP."
  type        = string
  default     = "g2-standard-16"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]+-[a-z]+-[0-9]+$", var.machine_type))
    error_message = "Must be a valid GCE machine type (e.g., g2-standard-16)."
  }
}

variable "min_instances" {
  description = "Minimum number of instances in the Managed Instance Group."
  type        = number
  default     = 1

  validation {
    condition     = var.min_instances >= 1 && var.min_instances <= 10
    error_message = "Minimum instances must be between 1 and 10."
  }
}

variable "max_instances" {
  description = "Maximum number of instances in the Managed Instance Group for autoscaling."
  type        = number
  default     = 3

  validation {
    condition     = var.max_instances >= 1 && var.max_instances <= 20
    error_message = "Maximum instances must be between 1 and 20."
  }
}

variable "container_image" {
  description = "Full Artifact Registry image URL for the Accord application container (e.g., us-central1-docker.pkg.dev/project/repo/image:tag)."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9.-]+/[a-z0-9._/-]+:[a-zA-Z0-9._-]+$", var.container_image))
    error_message = "Must be a valid container image URL with tag."
  }
}
