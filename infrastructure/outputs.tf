# =============================================================================
# Accord TEE Negotiation Engine - Root Outputs
# =============================================================================
# Key outputs from all modules for integration, DNS configuration, and
# operational reference.
# =============================================================================

# -----------------------------------------------------------------------------
# Network Outputs
# -----------------------------------------------------------------------------
output "vpc_id" {
  description = "The ID of the Accord VPC."
  value       = module.network.vpc_id
}

output "vpc_self_link" {
  description = "Self-link of the Accord VPC."
  value       = module.network.vpc_self_link
}

output "private_subnet_self_link" {
  description = "Self-link of the private subnet for Confidential VMs."
  value       = module.network.private_subnet_self_link
}

output "cloud_nat_ip" {
  description = "External IP address allocated for Cloud NAT egress."
  value       = module.network.cloud_nat_ip
}

# -----------------------------------------------------------------------------
# Security Outputs
# -----------------------------------------------------------------------------
output "kms_keyring_id" {
  description = "ID of the Cloud KMS keyring."
  value       = module.security.kms_keyring_id
}

output "kms_crypto_key_id" {
  description = "ID of the Cloud KMS crypto key for CMEK encryption."
  value       = module.security.kms_crypto_key_id
}

output "vm_service_account_email" {
  description = "Email of the Confidential VM service account."
  value       = module.security.vm_service_account_email
}

output "deploy_service_account_email" {
  description = "Email of the CI/CD deployment service account."
  value       = module.security.deploy_service_account_email
}

output "cloud_armor_policy_name" {
  description = "Name of the Cloud Armor security policy."
  value       = module.security.cloud_armor_policy_name
}

# -----------------------------------------------------------------------------
# Data Outputs
# -----------------------------------------------------------------------------
output "firestore_database_name" {
  description = "Name of the Firestore database."
  value       = module.data.firestore_database_name
}

output "audit_logs_bucket_name" {
  description = "Name of the Cloud Storage audit logs bucket."
  value       = module.data.audit_logs_bucket_name
}

output "audit_logs_bucket_url" {
  description = "URL of the Cloud Storage audit logs bucket."
  value       = module.data.audit_logs_bucket_url
}

output "documents_bucket_name" {
  description = "Name of the Cloud Storage documents bucket."
  value       = module.data.documents_bucket_name
}

output "documents_bucket_url" {
  description = "URL of the Cloud Storage documents bucket."
  value       = module.data.documents_bucket_url
}

# -----------------------------------------------------------------------------
# Compute Outputs
# -----------------------------------------------------------------------------
output "load_balancer_ip" {
  description = "External IP address of the HTTPS load balancer. Create a DNS A record pointing your domain to this IP."
  value       = module.compute.load_balancer_ip
}

output "managed_instance_group_name" {
  description = "Name of the Managed Instance Group."
  value       = module.compute.managed_instance_group_name
}

output "ssl_certificate_name" {
  description = "Name of the managed SSL certificate. Verify domain ownership for provisioning."
  value       = module.compute.ssl_certificate_name
}

output "health_check_name" {
  description = "Name of the HTTP health check."
  value       = module.compute.health_check_name
}

# -----------------------------------------------------------------------------
# Monitoring Outputs
# -----------------------------------------------------------------------------
output "log_sink_name" {
  description = "Name of the Cloud Logging sink for audit logs."
  value       = module.monitoring.log_sink_name
}

output "dashboard_name" {
  description = "Name of the Cloud Monitoring dashboard."
  value       = module.monitoring.dashboard_name
}

output "notification_channel_name" {
  description = "Name of the email notification channel."
  value       = module.monitoring.notification_channel_name
}

# -----------------------------------------------------------------------------
# DNS Configuration Instructions
# -----------------------------------------------------------------------------
output "dns_configuration" {
  description = "DNS configuration instructions for the domain."
  value       = "Create an A record for '${var.domain}' pointing to '${module.compute.load_balancer_ip}'. The managed SSL certificate will auto-provision once DNS propagates."
}
