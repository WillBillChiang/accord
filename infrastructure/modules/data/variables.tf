# =============================================================================
# Accord TEE Negotiation Engine - Data Module Variables
# =============================================================================

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for data resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "kms_key_id" {
  description = "Cloud KMS crypto key ID for CMEK encryption of Firestore and Cloud Storage."
  type        = string
}

variable "audit_retention_days" {
  description = "Retention period in days for the audit logs bucket (default: 7 years = 2555 days)."
  type        = number
  default     = 2555
}

variable "audit_nearline_transition_days" {
  description = "Days after which audit log objects transition to NEARLINE storage class."
  type        = number
  default     = 90
}

variable "audit_coldline_transition_days" {
  description = "Days after which audit log objects transition to COLDLINE storage class."
  type        = number
  default     = 365
}

variable "firestore_pitr_enabled" {
  description = "Enable point-in-time recovery for Firestore. Required for SOC 2 compliance."
  type        = bool
  default     = true
}
