# =============================================================================
# Accord TEE Negotiation Engine - Optional Domain Tests
# =============================================================================
# Validates that the domain variable is correctly optional for non-production
# environments and required for production (SOC 2 / ISO 27001 compliance).
#
# Run with: terraform test
# =============================================================================

# -----------------------------------------------------------------------------
# Test: Hackathon deployment without domain should succeed
# -----------------------------------------------------------------------------
run "hackathon_without_domain" {
  command = plan

  variables {
    project_id      = "accord-test-project"
    region          = "us-central1"
    zone            = "us-central1-a"
    environment     = "hackathon"
    alert_email     = "test@example.com"
    container_image = "us-central1-docker.pkg.dev/accord-test-project/accord/accord-app:latest"
    # domain is intentionally omitted (defaults to null)
  }

  assert {
    condition     = var.domain == null
    error_message = "Domain should default to null when not provided."
  }
}

# -----------------------------------------------------------------------------
# Test: Dev deployment without domain should succeed
# -----------------------------------------------------------------------------
run "dev_without_domain" {
  command = plan

  variables {
    project_id      = "accord-test-project"
    region          = "us-central1"
    zone            = "us-central1-a"
    environment     = "dev"
    alert_email     = "test@example.com"
    container_image = "us-central1-docker.pkg.dev/accord-test-project/accord/accord-app:latest"
  }

  assert {
    condition     = var.domain == null
    error_message = "Domain should default to null when not provided."
  }
}

# -----------------------------------------------------------------------------
# Test: Full config with domain should succeed
# -----------------------------------------------------------------------------
run "full_config_with_domain" {
  command = plan

  variables {
    project_id      = "accord-test-project"
    region          = "us-central1"
    zone            = "us-central1-a"
    environment     = "prod"
    domain          = "accord.example.com"
    alert_email     = "test@example.com"
    container_image = "us-central1-docker.pkg.dev/accord-test-project/accord/accord-app:latest"
  }

  assert {
    condition     = var.domain == "accord.example.com"
    error_message = "Domain should be set when provided."
  }
}
