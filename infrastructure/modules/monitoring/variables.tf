# =============================================================================
# Accord TEE Negotiation Engine - Monitoring Module Variables
# =============================================================================

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "alert_email" {
  description = "Email address for alert notifications."
  type        = string
}

variable "audit_logs_bucket_name" {
  description = "Name of the Cloud Storage audit logs bucket for log sink destination."
  type        = string
}

variable "error_rate_threshold" {
  description = "Threshold for high error rate alert (5xx count in 5 minutes)."
  type        = number
  default     = 5
}

variable "latency_threshold_ms" {
  description = "Threshold for high latency alert (p95 response time in milliseconds)."
  type        = number
  default     = 10000
}

variable "cpu_threshold_percent" {
  description = "Threshold for high CPU utilization alert (percentage)."
  type        = number
  default     = 80
}

variable "alert_alignment_period" {
  description = "Alignment period for alert policy metrics (in seconds)."
  type        = string
  default     = "300s"
}
