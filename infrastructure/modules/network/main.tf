# =============================================================================
# Accord TEE Negotiation Engine - Network Module
# =============================================================================
# Creates the VPC networking foundation:
#   - Custom-mode VPC with no default subnets
#   - Private subnet (10.0.10.0/24) for Confidential VMs with Private Google Access
#   - Public subnet (10.0.1.0/24) for Load Balancer (if needed)
#   - Cloud Router + Cloud NAT for private subnet egress
#   - Firewall rules: health checks, internal, IAP SSH, default deny ingress
#   - VPC Flow Logs enabled on all subnets (SOC 2 / ISO 27001)
# =============================================================================

locals {
  name_prefix = "accord-${var.environment}"

  labels = {
    project     = "accord"
    environment = var.environment
    module      = "network"
  }

  # Google health check source ranges
  health_check_ranges = ["130.211.0.0/22", "35.191.0.0/16"]

  # IAP TCP forwarding range for SSH management
  iap_range = ["35.235.240.0/20"]
}

# =============================================================================
# VPC
# =============================================================================
resource "google_compute_network" "vpc" {
  name                    = "${local.name_prefix}-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
  description             = "Accord ${var.environment} VPC - Confidential VM network with private subnets and Cloud NAT."
}

# =============================================================================
# Private Subnet (Confidential VMs)
# =============================================================================
resource "google_compute_subnetwork" "private" {
  name                     = "${local.name_prefix}-private-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.private_subnet_cidr
  private_ip_google_access = true
  description              = "Private subnet for Accord Confidential VM instances. No external IPs."

  log_config {
    aggregation_interval = var.flow_log_aggregation_interval
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
    filter_expr          = "true"
  }
}

# =============================================================================
# Public Subnet (Load Balancer / proxy-only)
# =============================================================================
resource "google_compute_subnetwork" "public" {
  name                     = "${local.name_prefix}-public-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = var.public_subnet_cidr
  private_ip_google_access = true
  description              = "Public subnet for Accord load balancer and proxy resources."

  log_config {
    aggregation_interval = var.flow_log_aggregation_interval
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
    filter_expr          = "true"
  }
}

# =============================================================================
# Cloud Router
# =============================================================================
resource "google_compute_router" "router" {
  name        = "${local.name_prefix}-router"
  project     = var.project_id
  region      = var.region
  network     = google_compute_network.vpc.id
  description = "Cloud Router for Accord ${var.environment} NAT gateway."

  bgp {
    asn = 64514
  }
}

# =============================================================================
# Cloud NAT (for private subnet egress)
# =============================================================================
resource "google_compute_address" "nat_ip" {
  name         = "${local.name_prefix}-nat-ip"
  project      = var.project_id
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"
  description  = "Static external IP for Accord Cloud NAT egress."
}

resource "google_compute_router_nat" "nat" {
  name                               = "${local.name_prefix}-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.router.name
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.nat_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "LIST_OF_SUBNETWORKS"

  subnetwork {
    name                    = google_compute_subnetwork.private.id
    source_ip_ranges_to_nat = ["ALL_IP_RANGES"]
  }

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }

  min_ports_per_vm                    = 256
  max_ports_per_vm                    = 4096
  enable_endpoint_independent_mapping = false

  # TCP/UDP timeouts for connection tracking
  tcp_established_idle_timeout_sec = 1200
  tcp_transitory_idle_timeout_sec  = 30
  udp_idle_timeout_sec             = 30
}

# =============================================================================
# Firewall Rules
# =============================================================================

# Allow Google health check probes to reach VMs on port 8080
resource "google_compute_firewall" "allow_health_check" {
  name        = "${local.name_prefix}-allow-health-check"
  project     = var.project_id
  network     = google_compute_network.vpc.id
  description = "Allow Google health check probes to Accord VMs on port 8080."
  direction   = "INGRESS"
  priority    = 1000

  source_ranges = local.health_check_ranges
  target_tags   = ["allow-health-check"]

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# Allow internal communication within the VPC CIDR
resource "google_compute_firewall" "allow_internal" {
  name        = "${local.name_prefix}-allow-internal"
  project     = var.project_id
  network     = google_compute_network.vpc.id
  description = "Allow all internal traffic within the Accord VPC."
  direction   = "INGRESS"
  priority    = 1100

  source_ranges = [var.vpc_cidr]

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# Allow SSH from IAP for management access
resource "google_compute_firewall" "allow_iap_ssh" {
  name        = "${local.name_prefix}-allow-iap-ssh"
  project     = var.project_id
  network     = google_compute_network.vpc.id
  description = "Allow SSH from Identity-Aware Proxy for secure management access."
  direction   = "INGRESS"
  priority    = 1200

  source_ranges = local.iap_range
  target_tags   = ["accord-vm"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# Deny all other ingress by default (explicit deny-all at low priority)
resource "google_compute_firewall" "deny_all_ingress" {
  name        = "${local.name_prefix}-deny-all-ingress"
  project     = var.project_id
  network     = google_compute_network.vpc.id
  description = "Deny all ingress traffic not matched by higher-priority rules. Defense in depth."
  direction   = "INGRESS"
  priority    = 65534

  source_ranges = ["0.0.0.0/0"]

  deny {
    protocol = "all"
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}
