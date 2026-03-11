# =============================================================================
# Accord TEE Negotiation Engine - Network Module Variables
# =============================================================================

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for network resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "vpc_cidr" {
  description = "Primary CIDR block for the VPC (used for internal firewall rules)."
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidr" {
  description = "CIDR range for the private subnet hosting Confidential VMs."
  type        = string
  default     = "10.0.10.0/24"
}

variable "public_subnet_cidr" {
  description = "CIDR range for the public subnet (load balancer proxy-only)."
  type        = string
  default     = "10.0.1.0/24"
}

variable "flow_log_aggregation_interval" {
  description = "VPC Flow Log aggregation interval. INTERVAL_5_MIN for compliance."
  type        = string
  default     = "INTERVAL_5_MIN"

  validation {
    condition     = contains(["INTERVAL_5_SEC", "INTERVAL_30_SEC", "INTERVAL_1_MIN", "INTERVAL_5_MIN", "INTERVAL_10_MIN", "INTERVAL_15_MIN"], var.flow_log_aggregation_interval)
    error_message = "Must be a valid flow log aggregation interval."
  }
}
