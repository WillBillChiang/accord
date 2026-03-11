# =============================================================================
# Accord TEE Negotiation Engine - Security Module Variables
# =============================================================================

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for security resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "kms_key_rotation_period" {
  description = "Rotation period for the Cloud KMS crypto key in seconds. Default: 90 days."
  type        = string
  default     = "7776000s"
}

variable "rate_limit_count" {
  description = "Maximum number of requests per rate limiting interval per IP."
  type        = number
  default     = 2000
}

variable "rate_limit_interval_sec" {
  description = "Rate limiting interval in seconds (5 minutes = 300 seconds)."
  type        = number
  default     = 300
}
