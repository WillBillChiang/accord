# =============================================================================
# Accord TEE Negotiation Engine - Security Module Outputs
# =============================================================================

output "kms_keyring_id" {
  description = "ID of the Cloud KMS keyring."
  value       = google_kms_key_ring.accord.id
}

output "kms_keyring_name" {
  description = "Name of the Cloud KMS keyring."
  value       = google_kms_key_ring.accord.name
}

output "kms_crypto_key_id" {
  description = "ID of the Cloud KMS crypto key for CMEK encryption."
  value       = google_kms_crypto_key.accord.id
}

output "kms_crypto_key_name" {
  description = "Name of the Cloud KMS crypto key."
  value       = google_kms_crypto_key.accord.name
}

output "vm_service_account_email" {
  description = "Email of the Confidential VM service account."
  value       = google_service_account.vm.email
}

output "vm_service_account_id" {
  description = "Fully qualified ID of the Confidential VM service account."
  value       = google_service_account.vm.id
}

output "deploy_service_account_email" {
  description = "Email of the CI/CD deployment service account."
  value       = google_service_account.deploy.email
}

output "deploy_service_account_id" {
  description = "Fully qualified ID of the CI/CD deployment service account."
  value       = google_service_account.deploy.id
}

output "cloud_armor_policy_self_link" {
  description = "Self-link of the Cloud Armor security policy."
  value       = google_compute_security_policy.accord.self_link
}

output "cloud_armor_policy_name" {
  description = "Name of the Cloud Armor security policy."
  value       = google_compute_security_policy.accord.name
}
