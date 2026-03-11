# =============================================================================
# Accord TEE Negotiation Engine - Monitoring Module Outputs
# =============================================================================

output "log_sink_name" {
  description = "Name of the Cloud Logging sink for audit logs."
  value       = google_logging_project_sink.audit_logs.name
}

output "log_sink_writer_identity" {
  description = "Writer identity of the log sink (service account)."
  value       = google_logging_project_sink.audit_logs.writer_identity
}

output "notification_channel_name" {
  description = "Name of the email notification channel."
  value       = google_monitoring_notification_channel.email.display_name
}

output "notification_channel_id" {
  description = "ID of the email notification channel."
  value       = google_monitoring_notification_channel.email.id
}

output "dashboard_name" {
  description = "Name of the Cloud Monitoring dashboard."
  value       = "Accord TEE Engine - ${var.environment}"
}

output "dashboard_id" {
  description = "ID of the Cloud Monitoring dashboard."
  value       = google_monitoring_dashboard.accord.id
}

output "alert_policy_high_error_rate_name" {
  description = "Name of the high error rate alert policy."
  value       = google_monitoring_alert_policy.high_error_rate.display_name
}

output "alert_policy_high_latency_name" {
  description = "Name of the high latency alert policy."
  value       = google_monitoring_alert_policy.high_latency.display_name
}

output "alert_policy_high_cpu_name" {
  description = "Name of the high CPU utilization alert policy."
  value       = google_monitoring_alert_policy.high_cpu.display_name
}

output "alert_policy_firestore_errors_name" {
  description = "Name of the Firestore errors alert policy."
  value       = google_monitoring_alert_policy.firestore_errors.display_name
}
