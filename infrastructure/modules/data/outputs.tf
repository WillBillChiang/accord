# =============================================================================
# Accord TEE Negotiation Engine - Data Module Outputs
# =============================================================================

output "firestore_database_name" {
  description = "Name of the Firestore database."
  value       = google_firestore_database.accord.name
}

output "firestore_database_id" {
  description = "Full resource ID of the Firestore database."
  value       = google_firestore_database.accord.id
}

output "audit_logs_bucket_name" {
  description = "Name of the Cloud Storage audit logs bucket."
  value       = google_storage_bucket.audit_logs.name
}

output "audit_logs_bucket_url" {
  description = "URL of the Cloud Storage audit logs bucket."
  value       = google_storage_bucket.audit_logs.url
}

output "audit_logs_bucket_self_link" {
  description = "Self-link of the Cloud Storage audit logs bucket."
  value       = google_storage_bucket.audit_logs.self_link
}

output "documents_bucket_name" {
  description = "Name of the Cloud Storage documents bucket."
  value       = google_storage_bucket.documents.name
}

output "documents_bucket_url" {
  description = "URL of the Cloud Storage documents bucket."
  value       = google_storage_bucket.documents.url
}

output "documents_bucket_self_link" {
  description = "Self-link of the Cloud Storage documents bucket."
  value       = google_storage_bucket.documents.self_link
}

output "audit_access_logs_bucket_name" {
  description = "Name of the access logs bucket for the audit logs bucket."
  value       = google_storage_bucket.audit_logs_access_logs.name
}
