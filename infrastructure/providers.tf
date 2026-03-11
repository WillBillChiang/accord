# =============================================================================
# Accord TEE Negotiation Engine - Provider Configuration
# =============================================================================
# Google Cloud Platform provider and Terraform version constraints.
# SOC 2 Type II / ISO 27001 compliant infrastructure.
# =============================================================================

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state backend - configure per environment
  # Uncomment and configure for production use:
  # backend "gcs" {
  #   bucket = "accord-terraform-state"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  default_labels = {
    project     = "accord"
    environment = var.environment
    managed_by  = "terraform"
    compliance  = "soc2-iso27001"
  }
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  default_labels = {
    project     = "accord"
    environment = var.environment
    managed_by  = "terraform"
    compliance  = "soc2-iso27001"
  }
}
