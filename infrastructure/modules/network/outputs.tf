# =============================================================================
# Accord TEE Negotiation Engine - Network Module Outputs
# =============================================================================

output "vpc_id" {
  description = "The ID of the Accord VPC."
  value       = google_compute_network.vpc.id
}

output "vpc_self_link" {
  description = "Self-link of the Accord VPC."
  value       = google_compute_network.vpc.self_link
}

output "vpc_name" {
  description = "Name of the Accord VPC."
  value       = google_compute_network.vpc.name
}

output "private_subnet_self_link" {
  description = "Self-link of the private subnet for Confidential VMs."
  value       = google_compute_subnetwork.private.self_link
}

output "private_subnet_name" {
  description = "Name of the private subnet."
  value       = google_compute_subnetwork.private.name
}

output "private_subnet_cidr" {
  description = "CIDR range of the private subnet."
  value       = google_compute_subnetwork.private.ip_cidr_range
}

output "public_subnet_self_link" {
  description = "Self-link of the public subnet."
  value       = google_compute_subnetwork.public.self_link
}

output "public_subnet_name" {
  description = "Name of the public subnet."
  value       = google_compute_subnetwork.public.name
}

output "cloud_router_name" {
  description = "Name of the Cloud Router."
  value       = google_compute_router.router.name
}

output "cloud_nat_name" {
  description = "Name of the Cloud NAT gateway."
  value       = google_compute_router_nat.nat.name
}

output "cloud_nat_ip" {
  description = "External IP address allocated for Cloud NAT."
  value       = google_compute_address.nat_ip.address
}
