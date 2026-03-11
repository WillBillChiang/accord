# =============================================================================
# Accord TEE Negotiation Engine - Monitoring Module
# =============================================================================
# Creates observability infrastructure:
#   - Cloud Logging sink: export admin/data access logs to audit bucket
#   - Alert policies: error rate, latency, CPU, Firestore errors
#   - Email notification channel
#   - Cloud Monitoring dashboard: requests, latency, errors, CPU, Firestore ops
#
# Compliance: SOC 2 Type II, ISO 27001
# =============================================================================

locals {
  name_prefix = "accord-${var.environment}"

  labels = {
    project     = "accord"
    environment = var.environment
    module      = "monitoring"
  }
}

# =============================================================================
# Notification Channel (Email)
# =============================================================================
resource "google_monitoring_notification_channel" "email" {
  display_name = "${local.name_prefix}-email-alerts"
  project      = var.project_id
  type         = "email"
  description  = "Email notification channel for Accord ${var.environment} alerts."

  labels = {
    email_address = var.alert_email
  }

  user_labels = local.labels

  enabled = true
}

# =============================================================================
# Cloud Logging Sink - Export audit logs to Cloud Storage
# =============================================================================
resource "google_logging_project_sink" "audit_logs" {
  name        = "${local.name_prefix}-audit-log-sink"
  project     = var.project_id
  destination = "storage.googleapis.com/${var.audit_logs_bucket_name}"
  description = "Export admin activity and data access logs to the audit logs bucket for SOC 2 / ISO 27001 compliance."

  # Export all admin activity and data access audit logs
  filter = <<-FILTER
    logName:"cloudaudit.googleapis.com"
    OR logName:"activity"
    OR logName:"data_access"
  FILTER

  unique_writer_identity = true
}

# Grant the log sink writer access to the audit bucket
resource "google_storage_bucket_iam_member" "log_sink_writer" {
  bucket = var.audit_logs_bucket_name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.audit_logs.writer_identity
}

# =============================================================================
# Alert Policy: High Error Rate (5xx > 5 in 5 minutes)
# =============================================================================
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "${local.name_prefix}-high-error-rate"
  project      = var.project_id
  combiner     = "OR"

  documentation {
    content   = "High 5xx error rate detected for the Accord ${var.environment} load balancer. More than ${var.error_rate_threshold} server errors in a 5-minute window. Investigate application logs and Confidential VM health immediately."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "5xx Error Count > ${var.error_rate_threshold}"

    condition_threshold {
      filter          = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code_class = \"500\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.error_rate_threshold
      duration        = "0s"

      aggregations {
        alignment_period   = var.alert_alignment_period
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  user_labels = local.labels
  enabled     = true
}

# =============================================================================
# Alert Policy: High Latency (p95 > 10 seconds)
# =============================================================================
resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "${local.name_prefix}-high-latency"
  project      = var.project_id
  combiner     = "OR"

  documentation {
    content   = "High latency detected for the Accord ${var.environment} load balancer. P95 response time exceeds ${var.latency_threshold_ms}ms. This may indicate TEE processing delays, GPU contention, or resource constraints."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "Backend Latency p95 > ${var.latency_threshold_ms}ms"

    condition_threshold {
      filter          = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/backend_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.latency_threshold_ms
      duration        = "300s"

      aggregations {
        alignment_period     = var.alert_alignment_period
        per_series_aligner   = "ALIGN_PERCENTILE_95"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  user_labels = local.labels
  enabled     = true
}

# =============================================================================
# Alert Policy: VM CPU Utilization > 80%
# =============================================================================
resource "google_monitoring_alert_policy" "high_cpu" {
  display_name = "${local.name_prefix}-high-cpu"
  project      = var.project_id
  combiner     = "OR"

  documentation {
    content   = "High CPU utilization detected on Accord ${var.environment} Confidential VMs. Average CPU exceeds ${var.cpu_threshold_percent}%. The autoscaler should handle this, but verify instance health and consider scaling limits."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "VM CPU Utilization > ${var.cpu_threshold_percent}%"

    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/cpu/utilization\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.cpu_threshold_percent / 100
      duration        = "900s"

      aggregations {
        alignment_period   = var.alert_alignment_period
        per_series_aligner = "ALIGN_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  user_labels = local.labels
  enabled     = true
}

# =============================================================================
# Alert Policy: Firestore Request Errors
# =============================================================================
resource "google_monitoring_alert_policy" "firestore_errors" {
  display_name = "${local.name_prefix}-firestore-errors"
  project      = var.project_id
  combiner     = "OR"

  documentation {
    content   = "Firestore request errors detected in the Accord ${var.environment} environment. Any Firestore errors are critical for compliance logging. Investigate immediately."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "Firestore Error Count > 0"

    condition_threshold {
      filter          = "resource.type = \"firestore.googleapis.com/Database\" AND metric.type = \"firestore.googleapis.com/document/request_count\" AND metric.labels.status != \"OK\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = var.alert_alignment_period
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }

  user_labels = local.labels
  enabled     = true
}

# =============================================================================
# Cloud Monitoring Dashboard
# =============================================================================
resource "google_monitoring_dashboard" "accord" {
  project        = var.project_id
  dashboard_json = jsonencode({
    displayName = "Accord TEE Engine - ${var.environment}"
    mosaicLayout = {
      columns = 48
      tiles = [
        # ---------------------------------------------------------------
        # Row 1: Title
        # ---------------------------------------------------------------
        {
          xPos   = 0
          yPos   = 0
          width  = 48
          height = 4
          widget = {
            title = ""
            text = {
              content = "# Accord TEE Negotiation Engine - ${var.environment}\nReal-time monitoring dashboard for the Accord infrastructure. SOC 2 / ISO 27001 compliant."
              format  = "MARKDOWN"
            }
          }
        },
        # ---------------------------------------------------------------
        # Row 2: Request Count + Latency
        # ---------------------------------------------------------------
        {
          xPos   = 0
          yPos   = 4
          width  = 24
          height = 16
          widget = {
            title = "Load Balancer Request Count"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_SUM"
                      }
                    }
                  }
                  plotType   = "LINE"
                  legendTemplate = "Request Count"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Requests"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 4
          width  = 24
          height = 16
          widget = {
            title = "Backend Latency (p50, p95, p99)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/backend_latencies\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_50"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "p50"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/backend_latencies\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_95"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "p95"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/backend_latencies\""
                      aggregation = {
                        alignmentPeriod    = "300s"
                        perSeriesAligner   = "ALIGN_PERCENTILE_99"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "p99"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Latency (ms)"
                scale = "LINEAR"
              }
            }
          }
        },
        # ---------------------------------------------------------------
        # Row 3: Error Rate + CPU
        # ---------------------------------------------------------------
        {
          xPos   = 0
          yPos   = 20
          width  = 24
          height = 16
          widget = {
            title = "HTTP Error Rate (4xx / 5xx)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code_class = \"500\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_SUM"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "5xx Errors"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code_class = \"400\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_SUM"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "4xx Errors"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Count"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 20
          width  = 24
          height = 16
          widget = {
            title = "VM CPU Utilization"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"gce_instance\" AND metric.type = \"compute.googleapis.com/instance/cpu/utilization\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_MEAN"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "CPU Utilization"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Utilization"
                scale = "LINEAR"
              }
            }
          }
        },
        # ---------------------------------------------------------------
        # Row 4: Firestore Ops + Cloud Armor
        # ---------------------------------------------------------------
        {
          xPos   = 0
          yPos   = 36
          width  = 24
          height = 16
          widget = {
            title = "Firestore Document Operations"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"firestore.googleapis.com/Database\" AND metric.type = \"firestore.googleapis.com/document/request_count\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_SUM"
                      }
                    }
                  }
                  plotType       = "STACKED_BAR"
                  legendTemplate = "$${metric.labels.op_type}"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Operations"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          xPos   = 24
          yPos   = 36
          width  = 24
          height = 16
          widget = {
            title = "Cloud Armor - Blocked Requests"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code = \"429\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_SUM"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "Rate Limited (429)"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type = \"https_lb_rule\" AND metric.type = \"loadbalancing.googleapis.com/https/request_count\" AND metric.labels.response_code = \"403\""
                      aggregation = {
                        alignmentPeriod  = "300s"
                        perSeriesAligner = "ALIGN_SUM"
                      }
                    }
                  }
                  plotType       = "LINE"
                  legendTemplate = "WAF Blocked (403)"
                }
              ]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Blocked Requests"
                scale = "LINEAR"
              }
            }
          }
        }
      ]
    }
  })
}
