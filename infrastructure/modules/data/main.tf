# =============================================================================
# Accord TEE Negotiation Engine - Data Module
# =============================================================================
# Creates data storage infrastructure:
#   - Firestore database (Native Mode) with CMEK encryption and PITR
#   - Cloud Storage: audit logs bucket with 7-year retention lock, lifecycle
#   - Cloud Storage: documents bucket with versioning and CMEK
#
# Collections managed by the application: sessions, audit_logs, users
#
# Compliance: SOC 2 Type II, ISO 27001
# =============================================================================

locals {
  name_prefix = "accord-${var.environment}"

  labels = {
    project     = "accord"
    environment = var.environment
    module      = "data"
  }
}

# =============================================================================
# Firestore Database (Native Mode)
# =============================================================================
resource "google_firestore_database" "accord" {
  project     = var.project_id
  name        = "accord-${var.environment}"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"

  point_in_time_recovery_enablement = var.firestore_pitr_enabled ? "POINT_IN_TIME_RECOVERY_ENABLED" : "POINT_IN_TIME_RECOVERY_DISABLED"

  cmek_config {
    kms_key_name = var.kms_key_id
  }

  delete_protection_state = "DELETE_PROTECTION_ENABLED"

  lifecycle {
    prevent_destroy = true
  }
}

# =============================================================================
# Firestore Indexes
# =============================================================================

# Sessions collection: query by createdBy, ordered by createdAt
resource "google_firestore_index" "sessions_created_by" {
  project    = var.project_id
  database   = google_firestore_database.accord.name
  collection = "sessions"

  fields {
    field_path = "createdBy"
    order      = "ASCENDING"
  }

  fields {
    field_path = "createdAt"
    order      = "DESCENDING"
  }
}

# Audit logs collection: query by sessionId, ordered by timestamp
resource "google_firestore_index" "audit_logs_session" {
  project    = var.project_id
  database   = google_firestore_database.accord.name
  collection = "audit_logs"

  fields {
    field_path = "sessionId"
    order      = "ASCENDING"
  }

  fields {
    field_path = "timestamp"
    order      = "DESCENDING"
  }
}

# =============================================================================
# Cloud Storage: Audit Logs Bucket
# =============================================================================
resource "google_storage_bucket" "audit_logs" {
  name     = "${local.name_prefix}-audit-logs-${var.project_id}"
  project  = var.project_id
  location = var.region
  labels   = merge(local.labels, {
    data_classification = "confidential"
    retention_policy    = "7-years"
  })

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = var.kms_key_id
  }

  # 7-year retention lock for compliance (SOC 2 / ISO 27001 audit trail)
  retention_policy {
    is_locked        = true
    retention_period = var.audit_retention_days * 86400 # Convert days to seconds
  }

  # Lifecycle rules for cost optimization
  lifecycle_rule {
    condition {
      age = var.audit_nearline_transition_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = var.audit_coldline_transition_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  # Prevent accidental deletion of audit data
  lifecycle {
    prevent_destroy = true
  }

  logging {
    log_bucket        = google_storage_bucket.audit_logs_access_logs.name
    log_object_prefix = "access-logs/"
  }
}

# Access logs bucket for the audit logs bucket (SOC 2 requirement)
resource "google_storage_bucket" "audit_logs_access_logs" {
  name     = "${local.name_prefix}-audit-access-logs-${var.project_id}"
  project  = var.project_id
  location = var.region
  labels   = merge(local.labels, {
    data_classification = "internal"
    purpose             = "access-logging"
  })

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  retention_policy {
    retention_period = 365 * 86400 # 1 year retention for access logs
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
}

# =============================================================================
# Cloud Storage: Documents Bucket
# =============================================================================
resource "google_storage_bucket" "documents" {
  name     = "${local.name_prefix}-documents-${var.project_id}"
  project  = var.project_id
  location = var.region
  labels   = merge(local.labels, {
    data_classification = "confidential"
  })

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = var.kms_key_id
  }

  lifecycle {
    prevent_destroy = true
  }
}
