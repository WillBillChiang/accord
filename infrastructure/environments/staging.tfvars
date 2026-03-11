# =============================================================================
# Accord TEE Negotiation Engine - Staging Environment
# =============================================================================
# Staging settings for pre-production validation and testing.
# Usage: terraform apply -var-file=environments/staging.tfvars
# =============================================================================

environment = "staging"
region      = "us-central1"
zone        = "us-central1-a"

# Compute - smaller footprint for cost savings in staging
machine_type  = "g2-standard-16"
min_instances = 1
max_instances = 2

# Override these per-deployment:
# project_id      = "accord-staging-project"
# domain          = "staging.accord.yourdomain.com"
# alert_email     = "dev-team@yourdomain.com"
# container_image = "us-central1-docker.pkg.dev/accord-staging-project/accord/tee-engine:staging"
