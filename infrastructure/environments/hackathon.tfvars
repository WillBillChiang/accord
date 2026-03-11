# =============================================================================
# Accord TEE Negotiation Engine - Hackathon Environment
# =============================================================================
# Cost-optimized settings for hackathons, demos, and short-lived deployments.
# Uses Spot VMs (~60-70% savings) and a smaller machine type.
#
# TEE (AMD SEV-SNP) and GPU (NVIDIA L4) inference remain fully functional.
# Spot VMs may be preempted by GCP — acceptable for hackathon use.
#
# Estimated cost: ~$21-24 for a 3-day hackathon.
#
# Usage: terraform apply -var-file=environments/hackathon.tfvars
# =============================================================================

environment = "hackathon"
region      = "us-central1"
zone        = "us-central1-a"

# Compute - cost-optimized with Spot VMs
machine_type  = "g2-standard-8"   # 8 vCPU, 32 GB RAM, 1x NVIDIA L4 GPU
min_instances = 1
max_instances = 1                  # No autoscaling — single instance
use_spot      = true               # ~60-70% cost savings vs on-demand

# Override these per-deployment:
# project_id      = "accord-hackathon-project"
# domain          = "hackathon.accord.yourdomain.com"
# alert_email     = "team@yourdomain.com"
# container_image = "us-central1-docker.pkg.dev/accord-hackathon-project/accord/accord-app:latest"
