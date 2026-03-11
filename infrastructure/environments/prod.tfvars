# =============================================================================
# Accord TEE Negotiation Engine - Production Environment
# =============================================================================
# Production-grade settings with high availability and compliance controls.
# Usage: terraform apply -var-file=environments/prod.tfvars
# =============================================================================

environment = "prod"
region      = "us-central1"
zone        = "us-central1-a"

# Compute - production sizing with autoscaling headroom
machine_type  = "g2-standard-16"
min_instances = 2
max_instances = 6

# Override these per-deployment:
# project_id      = "accord-prod-project"
# domain          = "accord.yourdomain.com"
# alert_email     = "sre-team@yourdomain.com"
# container_image = "us-central1-docker.pkg.dev/accord-prod-project/accord/tee-engine:v1.0.0"
