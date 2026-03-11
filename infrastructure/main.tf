# =============================================================================
# Accord TEE Negotiation Engine - Root Module
# =============================================================================
# Orchestrates all child modules to deploy the complete Accord infrastructure
# on Google Cloud Platform with Confidential VMs (AMD SEV-SNP + NVIDIA L4 GPU).
#
# Replaces 7 AWS CloudFormation templates:
#   - network.yaml    -> modules/network
#   - security.yaml   -> modules/security
#   - data.yaml       -> modules/data
#   - compute.yaml    -> modules/compute
#   - monitoring.yaml -> modules/monitoring
#   - auth.yaml       -> (handled by Identity Platform / external IdP)
#   - amplify.yaml    -> (handled by Cloud Run / external frontend hosting)
#
# Compliance: SOC 2 Type II, ISO 27001
# =============================================================================

# Enable required GCP APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "firestore.googleapis.com",
    "cloudkms.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "dns.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "artifactregistry.googleapis.com",
    "containeranalysis.googleapis.com",
    "certificatemanager.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# Network Module
# VPC, subnets, firewall rules, Cloud NAT, Cloud Router
# -----------------------------------------------------------------------------
module "network" {
  source = "./modules/network"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  depends_on = [google_project_service.required_apis]
}

# -----------------------------------------------------------------------------
# Security Module
# Cloud KMS, Service Accounts, IAM bindings, Cloud Armor
# -----------------------------------------------------------------------------
module "security" {
  source = "./modules/security"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  depends_on = [google_project_service.required_apis]
}

# -----------------------------------------------------------------------------
# Data Module
# Firestore (Native Mode), Cloud Storage buckets (audit + documents)
# -----------------------------------------------------------------------------
module "data" {
  source = "./modules/data"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  kms_key_id  = module.security.kms_crypto_key_id

  depends_on = [
    google_project_service.required_apis,
    module.security,
  ]
}

# -----------------------------------------------------------------------------
# Compute Module
# Confidential VM instance template, MIG, health check, HTTPS LB, autoscaler
# -----------------------------------------------------------------------------
module "compute" {
  source = "./modules/compute"

  project_id       = var.project_id
  region           = var.region
  zone             = var.zone
  environment      = var.environment
  domain           = var.domain
  machine_type     = var.machine_type
  min_instances    = var.min_instances
  max_instances    = var.max_instances
  container_image  = var.container_image
  network_self_link        = module.network.vpc_self_link
  private_subnet_self_link = module.network.private_subnet_self_link
  vm_service_account_email = module.security.vm_service_account_email
  kms_crypto_key_id        = module.security.kms_crypto_key_id
  cloud_armor_policy_self_link = module.security.cloud_armor_policy_self_link

  depends_on = [
    google_project_service.required_apis,
    module.network,
    module.security,
  ]
}

# -----------------------------------------------------------------------------
# Monitoring Module
# Log sinks, alert policies, notification channels, dashboard
# -----------------------------------------------------------------------------
module "monitoring" {
  source = "./modules/monitoring"

  project_id       = var.project_id
  region           = var.region
  environment      = var.environment
  alert_email      = var.alert_email
  audit_logs_bucket_name = module.data.audit_logs_bucket_name

  depends_on = [
    google_project_service.required_apis,
    module.data,
    module.compute,
  ]
}
