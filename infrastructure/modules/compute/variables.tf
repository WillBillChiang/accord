# =============================================================================
# Accord TEE Negotiation Engine - Compute Module Variables
# =============================================================================

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region for compute resources."
  type        = string
}

variable "zone" {
  description = "GCP zone for zonal compute resources (instance group, GPUs)."
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
}

variable "domain" {
  description = "Domain name for the managed SSL certificate."
  type        = string
}

variable "machine_type" {
  description = "GCE machine type for Confidential VM instances."
  type        = string
  default     = "g2-standard-16"
}

variable "min_instances" {
  description = "Minimum number of instances in the MIG."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum number of instances in the MIG."
  type        = number
  default     = 3
}

variable "container_image" {
  description = "Artifact Registry container image URL for the Accord application."
  type        = string
}

variable "network_self_link" {
  description = "Self-link of the VPC network."
  type        = string
}

variable "private_subnet_self_link" {
  description = "Self-link of the private subnet for VM instances."
  type        = string
}

variable "vm_service_account_email" {
  description = "Email of the VM service account."
  type        = string
}

variable "kms_crypto_key_id" {
  description = "Cloud KMS crypto key ID for CMEK encryption of boot disks."
  type        = string
}

variable "cloud_armor_policy_self_link" {
  description = "Self-link of the Cloud Armor security policy to attach to the backend service."
  type        = string
}

variable "boot_disk_size_gb" {
  description = "Size of the boot disk in GB."
  type        = number
  default     = 100
}

variable "boot_disk_type" {
  description = "Type of the boot disk."
  type        = string
  default     = "pd-ssd"
}

variable "gpu_type" {
  description = "Type of GPU accelerator."
  type        = string
  default     = "nvidia-l4"
}

variable "gpu_count" {
  description = "Number of GPUs per instance."
  type        = number
  default     = 1
}

variable "health_check_path" {
  description = "HTTP path for the health check endpoint."
  type        = string
  default     = "/health"
}

variable "health_check_port" {
  description = "Port for the health check and application traffic."
  type        = number
  default     = 8080
}

variable "autoscaler_target_cpu" {
  description = "Target CPU utilization for the autoscaler (0.0 to 1.0)."
  type        = number
  default     = 0.7
}

variable "cooldown_period_sec" {
  description = "Autoscaler cooldown period in seconds."
  type        = number
  default     = 300
}
