# =============================================================================
# Accord TEE Negotiation Engine - Compute Module Outputs
# =============================================================================

output "load_balancer_ip" {
  description = "External IP address of the HTTPS load balancer."
  value       = google_compute_global_address.lb_ip.address
}

output "managed_instance_group_name" {
  description = "Name of the Managed Instance Group."
  value       = google_compute_instance_group_manager.accord.name
}

output "managed_instance_group_id" {
  description = "ID of the Managed Instance Group."
  value       = google_compute_instance_group_manager.accord.id
}

output "managed_instance_group_instance_group" {
  description = "Instance group URL of the MIG (for backend service)."
  value       = google_compute_instance_group_manager.accord.instance_group
}

output "instance_template_id" {
  description = "ID of the Confidential VM instance template."
  value       = google_compute_instance_template.accord.id
}

output "instance_template_self_link" {
  description = "Self-link of the Confidential VM instance template."
  value       = google_compute_instance_template.accord.self_link
}

output "health_check_name" {
  description = "Name of the HTTP health check."
  value       = google_compute_health_check.accord.name
}

output "health_check_id" {
  description = "ID of the HTTP health check."
  value       = google_compute_health_check.accord.id
}

output "backend_service_name" {
  description = "Name of the backend service."
  value       = google_compute_backend_service.accord.name
}

output "backend_service_id" {
  description = "ID of the backend service."
  value       = google_compute_backend_service.accord.id
}

output "ssl_certificate_name" {
  description = "Name of the managed SSL certificate. Null when no domain is configured."
  value       = try(google_compute_managed_ssl_certificate.accord[0].name, null)
}

output "ssl_policy_name" {
  description = "Name of the SSL policy (TLS 1.2+). Null when no domain is configured."
  value       = try(google_compute_ssl_policy.accord[0].name, null)
}

output "url_map_name" {
  description = "Name of the URL map."
  value       = google_compute_url_map.accord.name
}

output "dns_zone_name" {
  description = "Name of the Cloud DNS managed zone. Null when no domain is configured."
  value       = try(google_dns_managed_zone.accord[0].name, null)
}

output "dns_zone_name_servers" {
  description = "Name servers for the Cloud DNS managed zone. Null when no domain is configured."
  value       = try(google_dns_managed_zone.accord[0].name_servers, null)
}

output "autoscaler_name" {
  description = "Name of the autoscaler."
  value       = google_compute_autoscaler.accord.name
}

output "access_url" {
  description = "URL to access the Accord application (HTTPS with domain, HTTP with IP when no domain)."
  value       = local.has_domain ? "https://${var.domain}" : "http://${google_compute_global_address.lb_ip.address}"
}
