# =============================================================================
# Accord TEE Negotiation Engine - Example Variable Values
# =============================================================================
# Copy this file and customize for your deployment.
# For environment-specific overrides, see environments/*.tfvars
#
# IMPORTANT: Do not commit sensitive values to version control.
# Use environment variables or a secrets manager for credentials.
# =============================================================================

project_id  = "your-gcp-project-id"
region      = "us-central1"
zone        = "us-central1-a"
environment = "prod"

# domain    = "accord.example.com"  # Optional for non-prod. Omit for HTTP-only access via LB IP.
alert_email = "ops-team@example.com"

machine_type   = "g2-standard-16"
min_instances  = 1
max_instances  = 3

container_image = "us-central1-docker.pkg.dev/your-gcp-project-id/accord/tee-engine:latest"
