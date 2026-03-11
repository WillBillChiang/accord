# =============================================================================
# Accord TEE Negotiation Engine - Security Module
# =============================================================================
# Creates security infrastructure:
#   - Cloud KMS Keyring and CryptoKey with 90-day rotation (CMEK)
#   - Service Accounts with least-privilege IAM bindings
#   - Cloud Armor security policy (rate limiting, OWASP rules)
#
# Compliance: SOC 2 Type II, ISO 27001
# =============================================================================

locals {
  name_prefix = "accord-${var.environment}"

  labels = {
    project     = "accord"
    environment = var.environment
    module      = "security"
  }
}

# =============================================================================
# Cloud KMS - Customer-Managed Encryption Keys
# =============================================================================
resource "google_kms_key_ring" "accord" {
  name     = "${local.name_prefix}-keyring"
  project  = var.project_id
  location = var.region
}

resource "google_kms_crypto_key" "accord" {
  name            = "${local.name_prefix}-key"
  key_ring        = google_kms_key_ring.accord.id
  rotation_period = var.kms_key_rotation_period
  purpose         = "ENCRYPT_DECRYPT"

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  labels = local.labels

  lifecycle {
    prevent_destroy = true
  }
}

# =============================================================================
# Service Accounts
# =============================================================================

# Service Account for Confidential VM instances
resource "google_service_account" "vm" {
  account_id   = "${local.name_prefix}-vm"
  project      = var.project_id
  display_name = "Accord ${var.environment} VM Service Account"
  description  = "Service account for Accord Confidential VM instances. Grants access to KMS, Firestore, Cloud Storage, and Cloud Logging."
}

# Service Account for CI/CD deployment
resource "google_service_account" "deploy" {
  account_id   = "${local.name_prefix}-deploy"
  project      = var.project_id
  display_name = "Accord ${var.environment} Deploy Service Account"
  description  = "Service account for Accord CI/CD deployment pipelines."
}

# =============================================================================
# IAM Bindings - VM Service Account (Least Privilege)
# =============================================================================

# Cloud KMS CryptoKey Decrypter - allows VM to decrypt with the CMEK key
resource "google_kms_crypto_key_iam_member" "vm_kms_decrypter" {
  crypto_key_id = google_kms_crypto_key.accord.id
  role          = "roles/cloudkms.cryptoKeyDecrypter"
  member        = "serviceAccount:${google_service_account.vm.email}"
}

# Cloud KMS CryptoKey Encrypter - allows VM to encrypt with the CMEK key
resource "google_kms_crypto_key_iam_member" "vm_kms_encrypter" {
  crypto_key_id = google_kms_crypto_key.accord.id
  role          = "roles/cloudkms.cryptoKeyEncrypter"
  member        = "serviceAccount:${google_service_account.vm.email}"
}

# Firestore User - read/write access to Firestore documents
resource "google_project_iam_member" "vm_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# Cloud Storage Object Admin - read/write to GCS buckets
resource "google_project_iam_member" "vm_storage_object_user" {
  project = var.project_id
  role    = "roles/storage.objectUser"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# Cloud Logging Writer - write application and audit logs
resource "google_project_iam_member" "vm_logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# Cloud Monitoring Metric Writer - publish custom metrics
resource "google_project_iam_member" "vm_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# Secret Manager Secret Accessor - read application secrets
resource "google_project_iam_member" "vm_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# Artifact Registry Reader - pull container images
resource "google_project_iam_member" "vm_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# =============================================================================
# IAM Bindings - Deploy Service Account
# =============================================================================

# Compute Admin - manage instance groups and templates
resource "google_project_iam_member" "deploy_compute_admin" {
  project = var.project_id
  role    = "roles/compute.admin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Artifact Registry Writer - push container images
resource "google_project_iam_member" "deploy_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Service Account User - impersonate the VM SA for deployments
resource "google_service_account_iam_member" "deploy_use_vm_sa" {
  service_account_id = google_service_account.vm.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# =============================================================================
# KMS IAM for GCP managed services (Firestore, Cloud Storage, Compute)
# =============================================================================

# Grant Firestore service agent access to the KMS key for CMEK
data "google_project" "current" {
  project_id = var.project_id
}

resource "google_kms_crypto_key_iam_member" "firestore_kms" {
  crypto_key_id = google_kms_crypto_key.accord.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-firestore.iam.gserviceaccount.com"
}

# Grant Cloud Storage service agent access to the KMS key for CMEK
resource "google_kms_crypto_key_iam_member" "storage_kms" {
  crypto_key_id = google_kms_crypto_key.accord.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.current.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# Grant Compute Engine service agent access to the KMS key for CMEK boot disks
resource "google_kms_crypto_key_iam_member" "compute_kms" {
  crypto_key_id = google_kms_crypto_key.accord.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.current.number}@compute-system.iam.gserviceaccount.com"
}

# =============================================================================
# Cloud Armor Security Policy
# =============================================================================
resource "google_compute_security_policy" "accord" {
  name        = "${local.name_prefix}-security-policy"
  project     = var.project_id
  description = "Cloud Armor security policy for Accord. Rate limiting (${var.rate_limit_count} req/${var.rate_limit_interval_sec}s), OWASP CRS, SQLi, and XSS protection."

  # -----------------------------------------------------------------------
  # Rule 1: Rate Limiting - 2000 requests per 5 minutes per IP
  # -----------------------------------------------------------------------
  rule {
    action   = "throttle"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = var.rate_limit_count
        interval_sec = var.rate_limit_interval_sec
      }
      enforce_on_key = "IP"
    }
    description = "Rate limit: ${var.rate_limit_count} requests per ${var.rate_limit_interval_sec} seconds per IP address."
  }

  # -----------------------------------------------------------------------
  # Rule 2: OWASP ModSecurity Core Rule Set (CRS)
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2000
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('sqli-v33-stable')"
      }
    }
    description = "Block SQL injection attacks using OWASP CRS SQLi rules."
  }

  # -----------------------------------------------------------------------
  # Rule 3: XSS Protection
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2100
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('xss-v33-stable')"
      }
    }
    description = "Block cross-site scripting (XSS) attacks using OWASP CRS XSS rules."
  }

  # -----------------------------------------------------------------------
  # Rule 4: Local File Inclusion (LFI) Protection
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2200
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('lfi-v33-stable')"
      }
    }
    description = "Block local file inclusion (LFI) attacks."
  }

  # -----------------------------------------------------------------------
  # Rule 5: Remote File Inclusion (RFI) Protection
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2300
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rfi-v33-stable')"
      }
    }
    description = "Block remote file inclusion (RFI) attacks."
  }

  # -----------------------------------------------------------------------
  # Rule 6: Remote Code Execution (RCE) Protection
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2400
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('rce-v33-stable')"
      }
    }
    description = "Block remote code execution (RCE) attacks."
  }

  # -----------------------------------------------------------------------
  # Rule 7: Scanner Detection
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2500
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('scannerdetection-v33-stable')"
      }
    }
    description = "Block known vulnerability scanner traffic."
  }

  # -----------------------------------------------------------------------
  # Rule 8: Protocol Attack Protection
  # -----------------------------------------------------------------------
  rule {
    action   = "deny(403)"
    priority = 2600
    match {
      expr {
        expression = "evaluatePreconfiguredWaf('protocolattack-v33-stable')"
      }
    }
    description = "Block HTTP protocol attack vectors."
  }

  # -----------------------------------------------------------------------
  # Default Rule: Allow all other traffic
  # -----------------------------------------------------------------------
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow rule. All traffic not matched by higher-priority rules is permitted."
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }
}
