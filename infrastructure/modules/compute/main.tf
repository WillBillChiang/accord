# =============================================================================
# Accord TEE Negotiation Engine - Compute Module
# =============================================================================
# Creates compute infrastructure:
#   - Instance template: Confidential VM (AMD SEV-SNP) + NVIDIA L4 GPU
#     with Shielded VM, CMEK boot disk, startup script
#   - Managed Instance Group (MIG) with auto-healing
#   - HTTP health check on /health:8080
#   - Backend service with Cloud Armor and session affinity
#   - URL map, HTTPS proxy, global forwarding rule
#   - Managed SSL certificate
#   - Autoscaler (CPU-based, min 1 / max 3)
#
# Compliance: SOC 2 Type II, ISO 27001
# =============================================================================

locals {
  name_prefix = "accord-${var.environment}"

  labels = {
    project     = "accord"
    environment = var.environment
    module      = "compute"
  }

  vm_tags = ["accord-vm", "allow-health-check"]

  has_domain = var.domain != null && var.domain != ""

  # Startup script installs NVIDIA drivers, Docker, pulls and runs the container
  startup_script = <<-STARTUP
    #!/bin/bash
    set -euo pipefail
    exec > >(tee /var/log/accord-startup.log) 2>&1

    echo "=== Accord TEE Engine Bootstrap ==="
    echo "Environment: ${var.environment}"
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

    # -----------------------------------------------------------------------
    # System Updates
    # -----------------------------------------------------------------------
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get upgrade -y

    # -----------------------------------------------------------------------
    # Install NVIDIA GPU Drivers (from CUDA repo)
    # -----------------------------------------------------------------------
    echo "Installing NVIDIA GPU drivers..."
    apt-get install -y linux-headers-$(uname -r) pciutils

    # Add NVIDIA CUDA repository
    distribution=$(. /etc/os-release; echo $ID$VERSION_ID | sed -e 's/\.//g')
    curl -fsSL https://developer.download.nvidia.com/compute/cuda/repos/$${distribution}/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/cuda-keyring.deb
    dpkg -i /tmp/cuda-keyring.deb
    apt-get update -y

    # Install NVIDIA driver and CUDA toolkit
    apt-get install -y nvidia-driver-550 nvidia-utils-550
    apt-get install -y nvidia-container-toolkit

    # Configure NVIDIA container runtime
    nvidia-ctk runtime configure --runtime=docker
    echo "NVIDIA driver installation complete."

    # -----------------------------------------------------------------------
    # Install and Configure Docker
    # -----------------------------------------------------------------------
    echo "Installing Docker..."
    apt-get install -y docker.io
    systemctl enable docker
    systemctl start docker

    # Configure Docker logging to limit disk usage
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json <<'DOCKEREOF'
    {
      "log-driver": "json-file",
      "log-opts": {
        "max-size": "100m",
        "max-file": "5"
      },
      "default-runtime": "nvidia",
      "runtimes": {
        "nvidia": {
          "path": "nvidia-container-runtime",
          "runtimeArgs": []
        }
      }
    }
    DOCKEREOF
    systemctl restart docker

    # -----------------------------------------------------------------------
    # Install Cloud Ops Agent for logging and monitoring
    # -----------------------------------------------------------------------
    echo "Installing Cloud Ops Agent..."
    curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
    bash add-google-cloud-ops-agent-repo.sh --also-install
    rm -f add-google-cloud-ops-agent-repo.sh

    # -----------------------------------------------------------------------
    # Authenticate and pull the container image
    # -----------------------------------------------------------------------
    echo "Pulling container image: ${var.container_image}..."
    gcloud auth configure-docker $(echo "${var.container_image}" | cut -d'/' -f1) --quiet
    docker pull "${var.container_image}"

    # -----------------------------------------------------------------------
    # Create application directories
    # -----------------------------------------------------------------------
    mkdir -p /var/log/accord
    chmod 755 /var/log/accord

    # -----------------------------------------------------------------------
    # Run the Accord TEE container with GPU access
    # -----------------------------------------------------------------------
    echo "Starting Accord container..."
    docker run -d \
      --name accord-tee \
      --restart unless-stopped \
      --gpus all \
      --network host \
      --log-driver json-file \
      --log-opt max-size=200m \
      --log-opt max-file=5 \
      -e ENVIRONMENT="${var.environment}" \
      -e PORT="${var.health_check_port}" \
      -e GCP_PROJECT="${var.project_id}" \
      -v /var/log/accord:/var/log/accord \
      "${var.container_image}"

    echo "=== Bootstrap Complete ==="
  STARTUP
}

# =============================================================================
# Static External IP for the Load Balancer
# =============================================================================
resource "google_compute_global_address" "lb_ip" {
  name         = "${local.name_prefix}-lb-ip"
  project      = var.project_id
  description  = "Static external IP for the Accord HTTPS load balancer."
  address_type = "EXTERNAL"
  ip_version   = "IPV4"
}

# =============================================================================
# Managed SSL Certificate
# =============================================================================
resource "google_compute_managed_ssl_certificate" "accord" {
  count   = local.has_domain ? 1 : 0
  name    = "${local.name_prefix}-ssl-cert"
  project = var.project_id

  managed {
    domains = [var.domain]
  }

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# Instance Template - Confidential VM with GPU
# =============================================================================
resource "google_compute_instance_template" "accord" {
  name_prefix  = "${local.name_prefix}-tpl-"
  project      = var.project_id
  region       = var.region
  machine_type = var.machine_type
  description  = "Accord Confidential VM template with AMD SEV-SNP, NVIDIA L4 GPU, and Shielded VM features."

  labels = local.labels
  tags   = local.vm_tags

  # Confidential Computing: AMD SEV-SNP
  confidential_instance_config {
    enable_confidential_compute = true
    confidential_instance_type  = "SEV_SNP"
  }

  # Shielded VM: Secure Boot, vTPM, Integrity Monitoring
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # GPU accelerator: NVIDIA L4
  guest_accelerator {
    type  = var.gpu_type
    count = var.gpu_count
  }

  # Required for GPU instances; Spot VMs reduce cost ~60-70% but may be preempted
  scheduling {
    on_host_maintenance          = "TERMINATE"
    automatic_restart            = var.use_spot ? false : true
    preemptible                  = var.use_spot
    provisioning_model           = var.use_spot ? "SPOT" : "STANDARD"
    instance_termination_action  = var.use_spot ? "STOP" : null
  }

  # Boot disk: SSD, CMEK encrypted
  disk {
    source_image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
    auto_delete  = true
    boot         = true
    disk_type    = var.boot_disk_type
    disk_size_gb = var.boot_disk_size_gb

    disk_encryption_key {
      kms_key_self_link = var.kms_crypto_key_id
    }

    labels = merge(local.labels, {
      disk_purpose = "boot"
    })
  }

  # Network: private subnet, no external IP
  network_interface {
    network    = var.network_self_link
    subnetwork = var.private_subnet_self_link
    # No access_config block = no external IP
  }

  # Service account with least-privilege scopes
  service_account {
    email  = var.vm_service_account_email
    scopes = ["cloud-platform"]
  }

  # Instance metadata
  metadata = {
    startup-script                = local.startup_script
    enable-oslogin                = "TRUE"
    block-project-ssh-keys        = "TRUE"
    serial-port-logging-enable    = "TRUE"
    google-logging-enabled        = "TRUE"
    google-monitoring-enabled     = "TRUE"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# Health Check
# =============================================================================
resource "google_compute_health_check" "accord" {
  name                = "${local.name_prefix}-health-check"
  project             = var.project_id
  description         = "HTTP health check for Accord application on port ${var.health_check_port}."
  check_interval_sec  = 15
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = var.health_check_port
    request_path = var.health_check_path
  }

  log_config {
    enable = true
  }
}

# =============================================================================
# Managed Instance Group (MIG)
# =============================================================================
resource "google_compute_instance_group_manager" "accord" {
  name               = "${local.name_prefix}-mig"
  project            = var.project_id
  zone               = var.zone
  base_instance_name = local.name_prefix
  description        = "Managed Instance Group for Accord Confidential VMs with auto-healing."

  version {
    instance_template = google_compute_instance_template.accord.id
    name              = "primary"
  }

  target_size = var.min_instances

  named_port {
    name = "http"
    port = var.health_check_port
  }

  auto_healing_policies {
    health_check      = google_compute_health_check.accord.id
    initial_delay_sec = 600 # 10 minutes for GPU driver installation + container pull
  }

  update_policy {
    type                         = "PROACTIVE"
    minimal_action               = "REPLACE"
    most_disruptive_allowed_action = "REPLACE"
    max_surge_fixed              = 1
    max_unavailable_fixed        = 0
    replacement_method           = "SUBSTITUTE"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# Autoscaler
# =============================================================================
resource "google_compute_autoscaler" "accord" {
  name        = "${local.name_prefix}-autoscaler"
  project     = var.project_id
  zone        = var.zone
  target      = google_compute_instance_group_manager.accord.id
  description = "CPU-based autoscaler for Accord MIG. Target: ${var.autoscaler_target_cpu * 100}% CPU."

  autoscaling_policy {
    min_replicas    = var.min_instances
    max_replicas    = var.max_instances
    cooldown_period = var.cooldown_period_sec

    cpu_utilization {
      target = var.autoscaler_target_cpu
    }
  }
}

# =============================================================================
# Backend Service
# =============================================================================
resource "google_compute_backend_service" "accord" {
  name                  = "${local.name_prefix}-backend"
  project               = var.project_id
  description           = "Backend service for Accord application with Cloud Armor and session affinity."
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 300
  health_checks         = [google_compute_health_check.accord.id]
  security_policy       = var.cloud_armor_policy_self_link
  session_affinity      = "GENERATED_COOKIE"
  affinity_cookie_ttl_sec = 86400 # 24 hours

  backend {
    group           = google_compute_instance_group_manager.accord.instance_group
    balancing_mode  = "UTILIZATION"
    capacity_scaler = 1.0
    max_utilization = 0.8
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }

  connection_draining_timeout_sec = 60
}

# =============================================================================
# URL Map
# =============================================================================
resource "google_compute_url_map" "accord" {
  name            = "${local.name_prefix}-url-map"
  project         = var.project_id
  description     = "URL map for Accord HTTPS load balancer."
  default_service = google_compute_backend_service.accord.id
}

# =============================================================================
# Target HTTPS Proxy
# =============================================================================
resource "google_compute_target_https_proxy" "accord" {
  count            = local.has_domain ? 1 : 0
  name             = "${local.name_prefix}-https-proxy"
  project          = var.project_id
  description      = "HTTPS proxy for Accord load balancer with managed SSL certificate."
  url_map          = google_compute_url_map.accord.id
  ssl_certificates = [google_compute_managed_ssl_certificate.accord[0].id]

  ssl_policy = google_compute_ssl_policy.accord[0].id
}

# =============================================================================
# SSL Policy (TLS 1.2+ only for compliance)
# =============================================================================
resource "google_compute_ssl_policy" "accord" {
  count           = local.has_domain ? 1 : 0
  name            = "${local.name_prefix}-ssl-policy"
  project         = var.project_id
  description     = "SSL policy enforcing TLS 1.2+ with MODERN profile for SOC 2 / ISO 27001 compliance."
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

# =============================================================================
# Global Forwarding Rule (HTTPS on port 443)
# =============================================================================
resource "google_compute_global_forwarding_rule" "accord_https" {
  count                 = local.has_domain ? 1 : 0
  name                  = "${local.name_prefix}-https-fwd-rule"
  project               = var.project_id
  description           = "Global forwarding rule for Accord HTTPS traffic on port 443."
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "443"
  target                = google_compute_target_https_proxy.accord[0].id
  load_balancing_scheme = "EXTERNAL"
}

# =============================================================================
# HTTP to HTTPS Redirect
# =============================================================================
resource "google_compute_url_map" "http_redirect" {
  count       = local.has_domain ? 1 : 0
  name        = "${local.name_prefix}-http-redirect"
  project     = var.project_id
  description = "URL map that redirects all HTTP traffic to HTTPS."

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "http_redirect" {
  count       = local.has_domain ? 1 : 0
  name        = "${local.name_prefix}-http-redirect-proxy"
  project     = var.project_id
  description = "HTTP proxy for HTTP-to-HTTPS redirect."
  url_map     = google_compute_url_map.http_redirect[0].id
}

resource "google_compute_global_forwarding_rule" "http_redirect" {
  count                 = local.has_domain ? 1 : 0
  name                  = "${local.name_prefix}-http-redirect-fwd-rule"
  project               = var.project_id
  description           = "Global forwarding rule that redirects HTTP (port 80) to HTTPS (port 443)."
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_target_http_proxy.http_redirect[0].id
  load_balancing_scheme = "EXTERNAL"
}

# =============================================================================
# Cloud DNS Managed Zone
# =============================================================================
resource "google_dns_managed_zone" "accord" {
  count       = local.has_domain ? 1 : 0
  name        = "${local.name_prefix}-dns-zone"
  project     = var.project_id
  dns_name    = "${var.domain}."
  description = "Cloud DNS managed zone for Accord ${var.environment} environment."
  visibility  = "public"

  dnssec_config {
    state = "on"
  }

  labels = local.labels
}

# A record pointing domain to the load balancer IP
resource "google_dns_record_set" "accord_a" {
  count        = local.has_domain ? 1 : 0
  name         = "${var.domain}."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.accord[0].name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.lb_ip.address]
}

# =============================================================================
# HTTP-only mode (when no domain is configured)
# Serves traffic on port 80 directly to the backend without SSL.
# Acceptable for hackathon/dev environments only.
# =============================================================================
resource "google_compute_target_http_proxy" "accord_http" {
  count       = local.has_domain ? 0 : 1
  name        = "${local.name_prefix}-http-proxy"
  project     = var.project_id
  description = "HTTP proxy for Accord load balancer (no-domain mode, no SSL)."
  url_map     = google_compute_url_map.accord.id
}

resource "google_compute_global_forwarding_rule" "accord_http" {
  count                 = local.has_domain ? 0 : 1
  name                  = "${local.name_prefix}-http-fwd-rule"
  project               = var.project_id
  description           = "Global forwarding rule for Accord HTTP traffic on port 80 (no-domain mode)."
  ip_address            = google_compute_global_address.lb_ip.address
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_target_http_proxy.accord_http[0].id
  load_balancing_scheme = "EXTERNAL"
}
