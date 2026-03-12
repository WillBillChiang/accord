# Accord Infrastructure -- Terraform Guide

| Field | Value |
|---|---|
| **Document Owner** | Infrastructure / SRE Team |
| **Classification** | Internal -- Confidential |
| **Compliance Scope** | SOC 2 Type II, ISO 27001 |
| **Last Updated** | 2026-03-11 |
| **Terraform Version** | >= 1.6.0 |
| **Cloud Provider** | Google Cloud Platform |

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites](#2-prerequisites)
3. [Module Architecture](#3-module-architecture)
4. [Getting Started](#4-getting-started)
5. [Environment Configuration](#5-environment-configuration)
6. [State Management](#6-state-management)
7. [Security Controls](#7-security-controls)
8. [Common Operations](#8-common-operations)
9. [CI/CD Integration](#9-cicd-integration)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Overview

The Accord infrastructure is defined as Terraform HCL across five modules under `infrastructure/`. This configuration replaces seven legacy AWS CloudFormation YAML templates:

| CloudFormation Template | Terraform Module | Notes |
|---|---|---|
| `network.yaml` | `modules/network` | VPC, subnets, Cloud NAT, firewall rules |
| `security.yaml` | `modules/security` | Cloud KMS, Service Accounts, IAM, Cloud Armor |
| `data.yaml` | `modules/data` | Firestore, Cloud Storage (audit + documents) |
| `compute.yaml` | `modules/compute` | Confidential VM template, MIG, HTTPS LB, autoscaler |
| `monitoring.yaml` | `modules/monitoring` | Logging sink, alert policies, dashboard |
| `auth.yaml` | *(external)* | Handled by Identity Platform / external IdP |
| `amplify.yaml` | *(external)* | Handled by Cloud Run / external frontend hosting |

All resources are deployed to GCP. Compute workloads run on Confidential VMs with AMD SEV-SNP and NVIDIA L4 GPUs. Every resource is tagged with `compliance = "soc2-iso27001"` via provider-level default labels.

### Repository Layout

```
infrastructure/
  main.tf                          # Root module -- orchestrates all child modules
  variables.tf                     # Root input variables with validation
  outputs.tf                       # Aggregated outputs from all modules
  providers.tf                     # Provider + backend configuration
  environments/
    prod.tfvars                    # Production variable overrides
    staging.tfvars                 # Staging variable overrides
  modules/
    network/
      main.tf                     # VPC, subnets, Cloud Router, Cloud NAT, firewall
      variables.tf                # Network-specific variables
      outputs.tf                  # VPC/subnet self-links, NAT IP
    security/
      main.tf                     # KMS, Service Accounts, IAM, Cloud Armor
      variables.tf                # KMS rotation period, rate limits
      outputs.tf                  # KMS key IDs, SA emails, Cloud Armor self-link
    data/
      main.tf                     # Firestore, audit logs bucket, documents bucket
      variables.tf                # Retention periods, PITR toggle
      outputs.tf                  # Database name, bucket names/URLs
    compute/
      main.tf                     # Instance template, MIG, health check, LB, DNS
      variables.tf                # Machine type, GPU, scaling, health check
      outputs.tf                  # LB IP, MIG name, SSL cert, DNS name servers
    monitoring/
      main.tf                     # Log sink, alert policies, notification channel, dashboard
      variables.tf                # Alert thresholds, alignment period
      outputs.tf                  # Sink name, alert policy names, dashboard ID
```

---

## 2. Prerequisites

### Required Software

| Tool | Minimum Version | Install |
|---|---|---|
| Terraform | >= 1.6.0 | [terraform.io/downloads](https://developer.hashicorp.com/terraform/downloads) |
| gcloud CLI | Latest | [cloud.google.com/sdk/install](https://cloud.google.com/sdk/docs/install) |
| git | >= 2.x | System package manager |

### Required Terraform Providers

These are pinned in `providers.tf` and downloaded automatically during `terraform init`:

| Provider | Version Constraint |
|---|---|
| `hashicorp/google` | `~> 5.0` |
| `hashicorp/google-beta` | `~> 5.0` |
| `hashicorp/random` | `~> 3.6` |

### GCP APIs to Enable

The root `main.tf` enables these APIs automatically via `google_project_service`, but they can also be enabled manually before first run to avoid race conditions:

```bash
PROJECT_ID="your-project-id"

gcloud services enable compute.googleapis.com \
  firestore.googleapis.com \
  cloudkms.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  dns.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com \
  servicenetworking.googleapis.com \
  artifactregistry.googleapis.com \
  containeranalysis.googleapis.com \
  certificatemanager.googleapis.com \
  --project="${PROJECT_ID}"
```

### GCP IAM Permissions

The user or service account running Terraform must have the following roles on the target project:

- `roles/owner` (for initial deployment), **or** the following granular roles:
  - `roles/compute.admin`
  - `roles/iam.serviceAccountAdmin`
  - `roles/iam.serviceAccountKeyAdmin`
  - `roles/cloudkms.admin`
  - `roles/storage.admin`
  - `roles/datastore.owner`
  - `roles/logging.admin`
  - `roles/monitoring.admin`
  - `roles/dns.admin`
  - `roles/serviceusage.serviceUsageAdmin`
  - `roles/resourcemanager.projectIamAdmin`

### Quota Requirements

Ensure the following quotas are sufficient in the target project and region (`us-central1`):

- **GPUs (NVIDIA L4)**: At least `max_instances` L4 GPUs (production default: 6)
- **g2-standard-16 CPUs**: `max_instances * 16` vCPUs
- **Persistent Disk SSD**: `max_instances * 100 GB`
- **External IP addresses**: 2 (1 for Cloud NAT, 1 for Load Balancer)
- **Backend services**: 1
- **SSL certificates**: 1

---

## 3. Module Architecture

### Dependency Graph

```
                    google_project_service.required_apis
                    (Enable 13 GCP APIs)
                           |
              +------------+------------+
              |                         |
        +-----v------+          +------v------+
        |  network   |          |  security   |
        |------------|          |-------------|
        | VPC        |          | KMS Keyring |
        | Subnets    |          | CryptoKey   |
        | Cloud NAT  |          | SAs + IAM   |
        | Firewall   |          | Cloud Armor |
        +-----+------+          +------+------+
              |                    |        |
              |         +----------+        |
              |         |                   |
        +-----v---------v--+        +------v------+
        |     compute      |        |    data     |
        |------------------|        |-------------|
        | Instance Template|        | Firestore   |
        | MIG + Autoscaler |        | Audit Bucket|
        | Health Check     |        | Docs Bucket |
        | HTTPS LB         |        +------+------+
        | SSL + DNS        |               |
        +---------+--------+               |
                  |                        |
           +------v------------------------v--+
           |          monitoring              |
           |----------------------------------|
           | Log Sink -> Audit Bucket         |
           | Alert Policies (4)               |
           | Email Notification Channel       |
           | Cloud Monitoring Dashboard       |
           +----------------------------------+
```

### Module Descriptions

#### `network` -- VPC and Connectivity

Creates the foundational networking layer with defense-in-depth firewall rules.

| Resource | Name Pattern | Purpose |
|---|---|---|
| `google_compute_network` | `accord-{env}-vpc` | Custom-mode VPC, no default subnets |
| `google_compute_subnetwork` (private) | `accord-{env}-private-subnet` | `10.0.10.0/24`, Private Google Access enabled, VPC Flow Logs |
| `google_compute_subnetwork` (public) | `accord-{env}-public-subnet` | `10.0.1.0/24`, for LB proxy, VPC Flow Logs |
| `google_compute_router` | `accord-{env}-router` | Cloud Router for NAT, BGP ASN 64514 |
| `google_compute_address` | `accord-{env}-nat-ip` | Static external IP for NAT egress |
| `google_compute_router_nat` | `accord-{env}-nat` | Cloud NAT for private subnet egress, error-only logging |
| `google_compute_firewall` (health check) | `accord-{env}-allow-health-check` | Allows `130.211.0.0/22`, `35.191.0.0/16` on TCP 8080 |
| `google_compute_firewall` (internal) | `accord-{env}-allow-internal` | Allows all protocols within `10.0.0.0/16` |
| `google_compute_firewall` (IAP SSH) | `accord-{env}-allow-iap-ssh` | Allows `35.235.240.0/20` on TCP 22 to `accord-vm` tagged instances |
| `google_compute_firewall` (deny all) | `accord-{env}-deny-all-ingress` | Explicit deny-all at priority 65534 |

All firewall rules have `log_config` enabled with `INCLUDE_ALL_METADATA` for compliance auditing.

#### `security` -- Identity, Encryption, and WAF

Creates the security control plane including encryption keys, service identities, and web application firewall rules.

| Resource | Name Pattern | Purpose |
|---|---|---|
| `google_kms_key_ring` | `accord-{env}-keyring` | KMS keyring in the deployment region |
| `google_kms_crypto_key` | `accord-{env}-key` | Symmetric encryption key, 90-day auto-rotation, `prevent_destroy = true` |
| `google_service_account` (VM) | `accord-{env}-vm` | Least-privilege SA for Confidential VM instances |
| `google_service_account` (Deploy) | `accord-{env}-deploy` | SA for CI/CD pipelines |
| `google_compute_security_policy` | `accord-{env}-security-policy` | Cloud Armor WAF policy |

**VM Service Account IAM Roles** (least privilege):

| Role | Purpose |
|---|---|
| `roles/cloudkms.cryptoKeyEncrypter` | Encrypt data with CMEK key |
| `roles/cloudkms.cryptoKeyDecrypter` | Decrypt data with CMEK key |
| `roles/datastore.user` | Read/write Firestore documents |
| `roles/storage.objectUser` | Read/write Cloud Storage objects |
| `roles/logging.logWriter` | Write application and audit logs |
| `roles/monitoring.metricWriter` | Publish custom metrics |
| `roles/secretmanager.secretAccessor` | Read application secrets |
| `roles/artifactregistry.reader` | Pull container images |

**Deploy Service Account IAM Roles**:

| Role | Purpose |
|---|---|
| `roles/compute.admin` | Manage instance groups and templates |
| `roles/artifactregistry.writer` | Push container images |
| `roles/iam.serviceAccountUser` | Impersonate the VM SA for deployments |

**Cloud Armor Rules** (in priority order):

| Priority | Rule | Action |
|---|---|---|
| 1000 | Rate limiting (2000 req / 300s per IP) | `throttle` / `deny(429)` |
| 2000 | OWASP CRS SQLi (`sqli-v33-stable`) | `deny(403)` |
| 2100 | XSS protection (`xss-v33-stable`) | `deny(403)` |
| 2200 | Local File Inclusion (`lfi-v33-stable`) | `deny(403)` |
| 2300 | Remote File Inclusion (`rfi-v33-stable`) | `deny(403)` |
| 2400 | Remote Code Execution (`rce-v33-stable`) | `deny(403)` |
| 2500 | Scanner Detection (`scannerdetection-v33-stable`) | `deny(403)` |
| 2600 | Protocol Attack (`protocolattack-v33-stable`) | `deny(403)` |
| 2147483647 | Default allow | `allow` |

Adaptive Protection Layer 7 DDoS defense is enabled.

#### `data` -- Persistence and Audit Trail

Creates data storage with CMEK encryption, retention locks, and lifecycle tiering.

| Resource | Name Pattern | Purpose |
|---|---|---|
| `google_firestore_database` | `accord-{env}` | Native mode, CMEK-encrypted, PITR enabled, delete protection |
| `google_firestore_index` (sessions) | -- | Composite index: `createdBy` ASC + `createdAt` DESC |
| `google_firestore_index` (audit_logs) | -- | Composite index: `sessionId` ASC + `timestamp` DESC |
| `google_storage_bucket` (audit) | `accord-{env}-audit-logs-{project_id}` | 7-year retention lock, CMEK, versioning, access logging |
| `google_storage_bucket` (access logs) | `accord-{env}-audit-access-logs-{project_id}` | 1-year retention for audit bucket access logs |
| `google_storage_bucket` (documents) | `accord-{env}-documents-{project_id}` | CMEK, versioning, public access prevention |

**Audit Logs Bucket Lifecycle**:

| Age (days) | Action |
|---|---|
| 90 | Transition to NEARLINE |
| 365 | Transition to COLDLINE |
| 2555 (7 years) | Retention lock expires |

All buckets enforce `uniform_bucket_level_access` and `public_access_prevention = "enforced"`.

#### `compute` -- Confidential VMs and Load Balancing

Creates the application runtime with Confidential Computing, GPU acceleration, and global HTTPS load balancing.

| Resource | Name Pattern | Purpose |
|---|---|---|
| `google_compute_instance_template` | `accord-{env}-tpl-*` | Confidential VM (AMD SEV-SNP), NVIDIA L4 GPU, Shielded VM, CMEK boot disk, OS Login |
| `google_compute_instance_group_manager` | `accord-{env}-mig` | Managed Instance Group with auto-healing (600s initial delay) |
| `google_compute_autoscaler` | `accord-{env}-autoscaler` | CPU-based autoscaling at 70% target utilization |
| `google_compute_health_check` | `accord-{env}-health-check` | HTTP check on `/health:8080`, 15s interval |
| `google_compute_backend_service` | `accord-{env}-backend` | Session affinity (generated cookie, 24h TTL), Cloud Armor attached |
| `google_compute_url_map` | `accord-{env}-url-map` | Default route to backend service |
| `google_compute_global_address` | `accord-{env}-lb-ip` | Static external IPv4 for the load balancer |
| `google_compute_target_https_proxy` | `accord-{env}-https-proxy` | HTTPS proxy with managed SSL cert and TLS 1.2+ policy *(domain only)* |
| `google_compute_ssl_policy` | `accord-{env}-ssl-policy` | MODERN profile, minimum TLS 1.2 *(domain only)* |
| `google_compute_managed_ssl_certificate` | `accord-{env}-ssl-cert` | Google-managed SSL cert for the domain *(domain only)* |
| `google_compute_global_forwarding_rule` (HTTPS) | `accord-{env}-https-fwd-rule` | Port 443 -> HTTPS proxy *(domain only)* |
| `google_compute_url_map` (redirect) | `accord-{env}-http-redirect` | HTTP-to-HTTPS 301 redirect *(domain only)* |
| `google_compute_target_http_proxy` (redirect) | `accord-{env}-http-redirect-proxy` | HTTP proxy for redirect *(domain only)* |
| `google_compute_global_forwarding_rule` (redirect) | `accord-{env}-http-redirect-fwd-rule` | Port 80 -> HTTP redirect proxy *(domain only)* |
| `google_dns_managed_zone` | `accord-{env}-dns-zone` | Cloud DNS zone with DNSSEC enabled *(domain only)* |
| `google_dns_record_set` | `{domain}.` | A record pointing to LB IP *(domain only)* |
| `google_compute_target_http_proxy` (HTTP-only) | `accord-{env}-http-proxy` | HTTP proxy for direct backend access *(no-domain only)* |
| `google_compute_global_forwarding_rule` (HTTP-only) | `accord-{env}-http-fwd-rule` | Port 80 -> HTTP proxy *(no-domain only)* |

**Instance Template Configuration**:

- **Machine type**: `g2-standard-16` (16 vCPUs, 64 GB RAM)
- **Boot image**: `ubuntu-2204-lts`
- **Boot disk**: 100 GB `pd-ssd`, CMEK-encrypted
- **GPU**: 1x NVIDIA L4
- **Confidential Computing**: AMD SEV-SNP
- **Shielded VM**: Secure Boot + vTPM + Integrity Monitoring
- **Network**: Private subnet only (no external IP), egress via Cloud NAT
- **OS Login**: Enabled, project SSH keys blocked
- **Startup**: Installs NVIDIA drivers (550), Docker with NVIDIA runtime, Cloud Ops Agent, pulls and runs the container

**MIG Update Policy**: Proactive rolling replace with `max_surge = 1`, `max_unavailable = 0` (zero-downtime).

#### `monitoring` -- Observability and Compliance Alerting

Creates the observability stack for operational and compliance monitoring.

| Resource | Name Pattern | Purpose |
|---|---|---|
| `google_monitoring_notification_channel` | `accord-{env}-email-alerts` | Email notification channel |
| `google_logging_project_sink` | `accord-{env}-audit-log-sink` | Exports admin activity + data access logs to audit bucket |
| `google_monitoring_alert_policy` (errors) | `accord-{env}-high-error-rate` | 5xx count > 5 in 5 minutes |
| `google_monitoring_alert_policy` (latency) | `accord-{env}-high-latency` | p95 backend latency > 10,000ms for 5 minutes |
| `google_monitoring_alert_policy` (CPU) | `accord-{env}-high-cpu` | VM CPU > 80% for 15 minutes |
| `google_monitoring_alert_policy` (Firestore) | `accord-{env}-firestore-errors` | Any Firestore request error |
| `google_monitoring_dashboard` | `Accord TEE Engine - {env}` | 6-panel dashboard (requests, latency, errors, CPU, Firestore ops, Cloud Armor) |

All alert policies auto-close after 30 minutes and send to the configured email channel.

---

## 4. Getting Started

### Step 1: Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### Step 2: Clone the Repository

```bash
git clone <repository-url>
cd accord/infrastructure
```

### Step 3: Create a Variable Override File

Copy one of the environment files and fill in the required values:

```bash
cp environments/staging.tfvars my-deploy.tfvars
```

Edit the file and set the required variables that have no defaults:

```hcl
# Required -- no defaults
project_id      = "accord-staging-project"
domain          = "staging.accord.yourdomain.com"
alert_email     = "dev-team@yourdomain.com"
container_image = "us-central1-docker.pkg.dev/accord-staging-project/accord/tee-engine:v1.0.0"

# Pre-set by the environment file
environment   = "staging"
region        = "us-central1"
zone          = "us-central1-a"
machine_type  = "g2-standard-16"
min_instances = 1
max_instances = 2
```

### Step 4: Initialize Terraform

```bash
terraform init
```

If using a remote GCS backend (see [State Management](#6-state-management)), initialize with backend configuration:

```bash
terraform init \
  -backend-config="bucket=accord-terraform-state-YOUR_PROJECT_ID" \
  -backend-config="prefix=terraform/state/staging"
```

### Step 5: Plan

```bash
terraform plan -var-file=environments/staging.tfvars \
  -var="project_id=accord-staging-project" \
  -var="domain=staging.accord.yourdomain.com" \
  -var="alert_email=dev-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-staging-project/accord/tee-engine:v1.0.0" \
  -out=tfplan
```

Review the plan output carefully. The initial deployment creates approximately 40-50 resources.

### Step 6: Apply

```bash
terraform apply tfplan
```

### Step 7: Configure DNS

After apply, Terraform outputs the load balancer IP and DNS zone name servers:

```bash
terraform output load_balancer_ip
```

If you are using Cloud DNS (managed by the compute module), configure your domain registrar to delegate to the Cloud DNS name servers. If you manage DNS externally, create an A record pointing your domain to the load balancer IP.

The managed SSL certificate will auto-provision once DNS propagates (allow up to 24 hours for initial provisioning).

Verify SSL certificate status:

```bash
gcloud compute ssl-certificates describe accord-staging-ssl-cert \
  --format="value(managed.status)"
```

---

## 5. Environment Configuration

### Variable Comparison: `prod.tfvars` vs `staging.tfvars`

| Variable | Production | Staging | Notes |
|---|---|---|---|
| `environment` | `prod` | `staging` | Controls all resource naming |
| `region` | `us-central1` | `us-central1` | Must support Confidential VMs + L4 GPUs |
| `zone` | `us-central1-a` | `us-central1-a` | Must support `g2-standard-16` |
| `machine_type` | `g2-standard-16` | `g2-standard-16` | Same machine type for parity |
| `min_instances` | `2` | `1` | Production runs a 2-instance minimum for HA |
| `max_instances` | `6` | `2` | Production has higher autoscaling headroom |

### Required Variables (No Defaults)

These must be supplied via `-var` flags, a `.tfvars` file, or environment variables:

| Variable | Description | Required | Example |
|---|---|---|---|
| `project_id` | GCP project ID | Always | `accord-prod-project` |
| `alert_email` | Email for monitoring alerts | Always | `sre-team@yourdomain.com` |
| `container_image` | Artifact Registry image URL with tag | Always | `us-central1-docker.pkg.dev/accord-prod-project/accord/tee-engine:v1.0.0` |
| `domain` | Domain for SSL cert and DNS | Prod only | `accord.yourdomain.com` |

> **Note:** The `domain` variable is optional for non-production environments (`dev`, `staging`, `hackathon`). When omitted, the load balancer serves HTTP-only traffic on port 80 via the static external IP. SSL certificate, DNS zone, and HTTP-to-HTTPS redirect resources are not created. Production deployments enforce `domain` via a Terraform `precondition` for SOC 2 / ISO 27001 TLS compliance.

### Module-Level Defaults

These defaults can be overridden in `.tfvars` files or via `-var` flags:

| Module | Variable | Default | Description |
|---|---|---|---|
| network | `vpc_cidr` | `10.0.0.0/16` | VPC address range |
| network | `private_subnet_cidr` | `10.0.10.0/24` | Confidential VM subnet |
| network | `public_subnet_cidr` | `10.0.1.0/24` | LB proxy subnet |
| network | `flow_log_aggregation_interval` | `INTERVAL_5_MIN` | VPC Flow Log interval |
| security | `kms_key_rotation_period` | `7776000s` (90 days) | CMEK key rotation |
| security | `rate_limit_count` | `2000` | Requests per rate limit window |
| security | `rate_limit_interval_sec` | `300` | Rate limit window (seconds) |
| data | `audit_retention_days` | `2555` (7 years) | Audit bucket retention lock |
| data | `audit_nearline_transition_days` | `90` | Days before NEARLINE tier |
| data | `audit_coldline_transition_days` | `365` | Days before COLDLINE tier |
| data | `firestore_pitr_enabled` | `true` | Point-in-time recovery |
| compute | `boot_disk_size_gb` | `100` | Boot disk size |
| compute | `boot_disk_type` | `pd-ssd` | Boot disk type |
| compute | `gpu_type` | `nvidia-l4` | GPU accelerator type |
| compute | `gpu_count` | `1` | GPUs per instance |
| compute | `health_check_path` | `/health` | Health check endpoint |
| compute | `health_check_port` | `8080` | Application port |
| compute | `autoscaler_target_cpu` | `0.7` | CPU target for autoscaler |
| compute | `cooldown_period_sec` | `300` | Autoscaler cooldown |
| monitoring | `error_rate_threshold` | `5` | 5xx count threshold |
| monitoring | `latency_threshold_ms` | `10000` | p95 latency threshold (ms) |
| monitoring | `cpu_threshold_percent` | `80` | CPU utilization threshold |
| monitoring | `alert_alignment_period` | `300s` | Metric aggregation window |

---

## 6. State Management

### Remote State with GCS Backend

The `providers.tf` file contains a commented-out GCS backend configuration. For production use, uncomment and configure it:

```hcl
terraform {
  backend "gcs" {
    bucket = "accord-terraform-state"
    prefix = "terraform/state/prod"
  }
}
```

### Setting Up the State Bucket

Create the state bucket manually before running `terraform init`. The bucket itself must not be managed by the same Terraform configuration it stores state for.

```bash
PROJECT_ID="accord-prod-project"
BUCKET_NAME="accord-terraform-state-${PROJECT_ID}"

# Create the bucket with versioning and uniform access
gsutil mb -p "${PROJECT_ID}" -l us-central1 -b on "gs://${BUCKET_NAME}"

# Enable versioning for state file history
gsutil versioning set on "gs://${BUCKET_NAME}"

# Set a lifecycle rule to delete old state versions (keep 10 most recent)
cat > /tmp/lifecycle.json << 'EOF'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"numNewerVersions": 10, "isLive": false}
    }
  ]
}
EOF
gsutil lifecycle set /tmp/lifecycle.json "gs://${BUCKET_NAME}"
rm /tmp/lifecycle.json

# Restrict access to Terraform operators only
gsutil iam ch \
  serviceAccount:accord-prod-deploy@${PROJECT_ID}.iam.gserviceaccount.com:roles/storage.objectAdmin \
  "gs://${BUCKET_NAME}"
```

### State Locking

GCS backends support native state locking via object metadata. No additional configuration is required -- Terraform will automatically acquire and release locks during `plan` and `apply` operations.

If a lock becomes stale (e.g., operator's process was killed):

```bash
# Inspect the lock
terraform force-unlock LOCK_ID
```

**WARNING**: Only use `force-unlock` if you are certain no other Terraform process is running against this state.

### Per-Environment State Isolation

Use separate `prefix` values to isolate state per environment:

| Environment | Backend Prefix |
|---|---|
| Production | `terraform/state/prod` |
| Staging | `terraform/state/staging` |

This ensures that a `terraform destroy` in staging cannot affect production resources.

### State Inspection and Backup

```bash
# List all resources in state
terraform state list

# Show a specific resource
terraform state show 'module.compute.google_compute_instance_template.accord'

# Pull the state file for backup
terraform state pull > state-backup-$(date +%Y%m%d).json
```

---

## 7. Security Controls

This section maps Terraform-managed resources to SOC 2 Type II Trust Service Criteria and ISO 27001 Annex A controls.

### 7.1 Encryption at Rest (SOC 2 CC6.1 / ISO 27001 A.10.1)

| Resource | Encryption Method | Key Rotation |
|---|---|---|
| Firestore database | CMEK (`google_kms_crypto_key`) | 90-day automatic rotation |
| Audit logs bucket | CMEK | 90-day automatic rotation |
| Documents bucket | CMEK | 90-day automatic rotation |
| Confidential VM boot disk | CMEK | 90-day automatic rotation |
| VM memory | AMD SEV-SNP hardware encryption | N/A (hardware-managed) |

The KMS key has `prevent_destroy = true` to prevent accidental key deletion that would render encrypted data unrecoverable.

GCP managed service agents (Firestore, Cloud Storage, Compute Engine) are granted `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the CMEK key via dedicated IAM bindings in the security module.

### 7.2 Encryption in Transit (SOC 2 CC6.1 / ISO 27001 A.13.1)

| Control | Implementation |
|---|---|
| TLS minimum version | TLS 1.2 enforced via `google_compute_ssl_policy` (MODERN profile) |
| SSL certificates | Google-managed certificates with auto-renewal |
| HTTP-to-HTTPS redirect | Dedicated URL map with `301 Moved Permanently` |
| DNSSEC | Enabled on the Cloud DNS managed zone |

### 7.3 Network Segmentation (SOC 2 CC6.6 / ISO 27001 A.13.1)

| Control | Implementation |
|---|---|
| Private subnets | VMs deployed in `10.0.10.0/24` with no external IPs |
| Private Google Access | Enabled on private subnet for GCP API access without public IP |
| Cloud NAT | Controlled egress via static IP with error-only logging |
| Default deny | Explicit deny-all ingress firewall rule at priority 65534 |
| VPC Flow Logs | Enabled on all subnets with `INCLUDE_ALL_METADATA`, 50% sampling |
| IAP-only SSH | SSH access restricted to IAP range (`35.235.240.0/20`) |

### 7.4 Identity and Access Management (SOC 2 CC6.2-CC6.3 / ISO 27001 A.9)

| Control | Implementation |
|---|---|
| Least-privilege service accounts | VM SA has only the 8 roles needed for application operation |
| Separation of duties | Separate VM and Deploy service accounts with distinct permissions |
| OS Login | Enabled on all instances, project SSH keys blocked |
| IAP SSH tunneling | SSH access audited through IAP, no direct SSH from internet |
| Service account impersonation | Deploy SA can impersonate VM SA only via `iam.serviceAccountUser` |

### 7.5 Web Application Security (SOC 2 CC6.6 / ISO 27001 A.14.1)

| Control | Cloud Armor Rule Priority |
|---|---|
| Rate limiting (2000 req / 5 min per IP) | 1000 |
| SQL injection (OWASP CRS v3.3) | 2000 |
| Cross-site scripting (OWASP CRS v3.3) | 2100 |
| Local file inclusion | 2200 |
| Remote file inclusion | 2300 |
| Remote code execution | 2400 |
| Scanner detection | 2500 |
| Protocol attacks | 2600 |
| Adaptive Protection (L7 DDoS) | Automatic |

### 7.6 Audit Logging (SOC 2 CC7.2 / ISO 27001 A.12.4)

| Control | Implementation |
|---|---|
| Admin activity logs | Exported to audit bucket via Cloud Logging sink |
| Data access logs | Exported to audit bucket via Cloud Logging sink |
| Firewall rule logging | All rules log with `INCLUDE_ALL_METADATA` |
| Load balancer logging | Backend service logs at 100% sample rate |
| Health check logging | Enabled on health check resource |
| NAT logging | Error-only logging enabled |
| Audit bucket access logs | Separate bucket for audit-on-audit |
| Audit retention | 7-year locked retention policy on audit bucket |
| Immutability | Retention lock is `is_locked = true` (cannot be shortened) |

### 7.7 Availability and Recovery (SOC 2 CC7.5 / ISO 27001 A.17)

| Control | Implementation |
|---|---|
| Auto-healing | MIG auto-healing with 600-second initial delay |
| Autoscaling | CPU-based autoscaler (70% target) with configurable min/max |
| Zero-downtime deploys | Rolling update: `max_surge = 1`, `max_unavailable = 0` |
| Point-in-time recovery | Firestore PITR enabled |
| Data versioning | Object versioning on all Cloud Storage buckets |
| Delete protection | Firestore, KMS key, audit bucket, and documents bucket have `prevent_destroy` |

### 7.8 Confidential Computing (SOC 2 CC6.7 / ISO 27001 A.10.1)

| Control | Implementation |
|---|---|
| Memory encryption | AMD SEV-SNP (`confidential_instance_type = "SEV_SNP"`) |
| Secure Boot | Enabled via `shielded_instance_config` |
| vTPM | Enabled for measured boot and integrity verification |
| Integrity Monitoring | Enabled to detect boot-time tampering |

### 7.9 Resource Labeling (ISO 27001 A.8.1)

All resources are tagged via provider-level `default_labels`:

```hcl
default_labels = {
  project     = "accord"
  environment = var.environment
  managed_by  = "terraform"
  compliance  = "soc2-iso27001"
}
```

Modules add `module`-level labels and data-classification labels where applicable (e.g., `data_classification = "confidential"` on the audit and documents buckets).

---

## 8. Common Operations

### 8.1 Scaling the MIG

**Adjust autoscaler limits** by modifying the variables and applying:

```bash
# Scale production to 3-10 instances
terraform apply -var-file=environments/prod.tfvars \
  -var="project_id=accord-prod-project" \
  -var="domain=accord.yourdomain.com" \
  -var="alert_email=sre-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-prod-project/accord/tee-engine:v1.0.0" \
  -var="min_instances=3" \
  -var="max_instances=10"
```

**Manually resize** the MIG (temporary, will revert on next `terraform apply`):

```bash
gcloud compute instance-groups managed resize accord-prod-mig \
  --size=4 \
  --zone=us-central1-a \
  --project=accord-prod-project
```

### 8.2 Updating the Container Image

Deploy a new application version by updating the `container_image` variable:

```bash
terraform plan -var-file=environments/prod.tfvars \
  -var="project_id=accord-prod-project" \
  -var="domain=accord.yourdomain.com" \
  -var="alert_email=sre-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-prod-project/accord/tee-engine:v1.1.0" \
  -out=tfplan

terraform apply tfplan
```

This creates a new instance template and triggers a rolling replacement of all instances in the MIG (zero-downtime due to `max_surge = 1`, `max_unavailable = 0`).

### 8.3 Rotating KMS Keys

KMS keys rotate automatically every 90 days (`7776000s`). To trigger an immediate manual rotation:

```bash
# Create a new key version (becomes the primary version)
gcloud kms keys versions create \
  --key=accord-prod-key \
  --keyring=accord-prod-keyring \
  --location=us-central1 \
  --project=accord-prod-project

# Verify the new primary version
gcloud kms keys describe accord-prod-key \
  --keyring=accord-prod-keyring \
  --location=us-central1 \
  --project=accord-prod-project \
  --format="value(primary.name)"
```

Existing data encrypted with older key versions remains accessible because KMS retains all enabled key versions for decryption.

To change the rotation period via Terraform:

```bash
terraform apply -var-file=environments/prod.tfvars \
  -var="project_id=accord-prod-project" \
  -var="domain=accord.yourdomain.com" \
  -var="alert_email=sre-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-prod-project/accord/tee-engine:v1.0.0" \
  -var="kms_key_rotation_period=5184000s"  # 60 days
```

### 8.4 Viewing Logs and Alerts

```bash
# View recent application logs
gcloud logging read \
  'resource.type="gce_instance" AND logName:"accord"' \
  --project=accord-prod-project \
  --limit=50 \
  --format="table(timestamp,jsonPayload.message)"

# View Cloud Armor blocked requests
gcloud logging read \
  'resource.type="http_load_balancer" AND httpRequest.status=403' \
  --project=accord-prod-project \
  --limit=20

# List active alert incidents
gcloud alpha monitoring policies list \
  --project=accord-prod-project \
  --filter="displayName:accord-prod"

# Open the monitoring dashboard
echo "https://console.cloud.google.com/monitoring/dashboards?project=accord-prod-project"
```

### 8.5 SSH Access via IAP

```bash
gcloud compute ssh INSTANCE_NAME \
  --zone=us-central1-a \
  --project=accord-prod-project \
  --tunnel-through-iap
```

### 8.6 Destroying Infrastructure

**WARNING**: Several resources have `prevent_destroy = true` (KMS key, Firestore database, audit bucket, documents bucket). To destroy them, you must first remove the lifecycle block in the Terraform code, apply, then destroy.

```bash
# Preview what will be destroyed
terraform plan -destroy -var-file=environments/staging.tfvars \
  -var="project_id=accord-staging-project" \
  -var="domain=staging.accord.yourdomain.com" \
  -var="alert_email=dev-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-staging-project/accord/tee-engine:staging"

# Destroy (staging only -- NEVER run against production without change approval)
terraform destroy -var-file=environments/staging.tfvars \
  -var="project_id=accord-staging-project" \
  -var="domain=staging.accord.yourdomain.com" \
  -var="alert_email=dev-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-staging-project/accord/tee-engine:staging"
```

Resources with `prevent_destroy` will cause the destroy to fail intentionally. This is a compliance safeguard. Overriding requires approval and documentation per the change management policy.

---

## 9. CI/CD Integration

### Pipeline Architecture

The recommended CI/CD flow uses the `accord-{env}-deploy` service account created by the security module:

```
PR Opened/Updated          PR Merged to main
       |                          |
  terraform fmt -check       terraform init
  terraform validate         terraform plan -out=tfplan
  terraform plan             (manual approval gate)
       |                     terraform apply tfplan
  Post plan as PR comment    Post apply output to Slack/email
```

### GitHub Actions Example

```yaml
# .github/workflows/terraform.yml
name: Terraform

on:
  pull_request:
    paths:
      - 'infrastructure/**'
  push:
    branches: [main]
    paths:
      - 'infrastructure/**'

env:
  TF_VERSION: '1.6.0'
  WORKING_DIR: 'infrastructure'

jobs:
  terraform-plan:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.DEPLOY_SA_EMAIL }}

      - name: Terraform Init
        working-directory: ${{ env.WORKING_DIR }}
        run: |
          terraform init \
            -backend-config="bucket=${{ secrets.TF_STATE_BUCKET }}" \
            -backend-config="prefix=terraform/state/prod"

      - name: Terraform Format Check
        working-directory: ${{ env.WORKING_DIR }}
        run: terraform fmt -check -recursive

      - name: Terraform Validate
        working-directory: ${{ env.WORKING_DIR }}
        run: terraform validate

      - name: Terraform Plan
        id: plan
        working-directory: ${{ env.WORKING_DIR }}
        run: |
          terraform plan \
            -var-file=environments/prod.tfvars \
            -var="project_id=${{ secrets.GCP_PROJECT_ID }}" \
            -var="domain=${{ secrets.DOMAIN }}" \
            -var="alert_email=${{ secrets.ALERT_EMAIL }}" \
            -var="container_image=${{ secrets.CONTAINER_IMAGE }}" \
            -no-color -out=tfplan
        continue-on-error: true

      - name: Post Plan to PR
        uses: actions/github-script@v7
        with:
          script: |
            const output = `#### Terraform Plan \`${{ steps.plan.outcome }}\`

            <details><summary>Show Plan</summary>

            \`\`\`
            ${{ steps.plan.outputs.stdout }}
            \`\`\`

            </details>

            *Pushed by: @${{ github.actor }}, Action: \`${{ github.event_name }}\`*`;

            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: output
            });

      - name: Fail on Plan Error
        if: steps.plan.outcome == 'failure'
        run: exit 1

  terraform-apply:
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval in GitHub
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.DEPLOY_SA_EMAIL }}

      - name: Terraform Init
        working-directory: ${{ env.WORKING_DIR }}
        run: |
          terraform init \
            -backend-config="bucket=${{ secrets.TF_STATE_BUCKET }}" \
            -backend-config="prefix=terraform/state/prod"

      - name: Terraform Apply
        working-directory: ${{ env.WORKING_DIR }}
        run: |
          terraform apply -auto-approve \
            -var-file=environments/prod.tfvars \
            -var="project_id=${{ secrets.GCP_PROJECT_ID }}" \
            -var="domain=${{ secrets.DOMAIN }}" \
            -var="alert_email=${{ secrets.ALERT_EMAIL }}" \
            -var="container_image=${{ secrets.CONTAINER_IMAGE }}"
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `WIF_PROVIDER` | Workload Identity Federation provider resource name |
| `DEPLOY_SA_EMAIL` | `accord-prod-deploy@PROJECT_ID.iam.gserviceaccount.com` |
| `TF_STATE_BUCKET` | GCS bucket for Terraform state |
| `GCP_PROJECT_ID` | Target GCP project ID |
| `DOMAIN` | Domain for SSL certificate |
| `ALERT_EMAIL` | Alert notification email |
| `CONTAINER_IMAGE` | Full Artifact Registry image URL with tag |

### Workload Identity Federation Setup

Use Workload Identity Federation instead of service account keys (no long-lived credentials):

```bash
PROJECT_ID="accord-prod-project"
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')
GITHUB_ORG="your-github-org"
GITHUB_REPO="accord"

# Create the WIF pool
gcloud iam workload-identity-pools create "github-pool" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Create the WIF provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project="${PROJECT_ID}" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Allow the deploy SA to be impersonated by GitHub Actions
gcloud iam service-accounts add-iam-policy-binding \
  "accord-prod-deploy@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="${PROJECT_ID}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}"
```

---

## 10. Troubleshooting

### SSL Certificate Stuck in PROVISIONING

**Symptom**: `terraform output ssl_certificate_name` shows the cert, but HTTPS returns errors.

**Cause**: DNS has not propagated or NS records at the registrar do not match Cloud DNS name servers.

**Resolution**:

```bash
# Check certificate status
gcloud compute ssl-certificates describe accord-prod-ssl-cert \
  --format="yaml(managed)" \
  --project=accord-prod-project

# Verify DNS resolution
dig +short accord.yourdomain.com

# Compare registrar NS records with Cloud DNS
terraform output -json | jq -r '.dns_zone_name_servers.value[]' 2>/dev/null
dig +short NS accord.yourdomain.com
```

The managed certificate requires DNS validation and can take up to 24 hours to provision initially.

### Instance Template Changes Not Rolling Out

**Symptom**: `terraform apply` succeeds but MIG instances are not being replaced.

**Cause**: The MIG update policy is `PROACTIVE` but Terraform may not detect the template change if only the startup script changed within the same template name prefix.

**Resolution**:

```bash
# Force a rolling update manually
gcloud compute instance-groups managed rolling-action replace accord-prod-mig \
  --zone=us-central1-a \
  --project=accord-prod-project \
  --max-surge=1 \
  --max-unavailable=0
```

### GPU Quota Exceeded

**Symptom**: `terraform apply` fails with `QUOTA_EXCEEDED` for GPUs.

**Resolution**:

```bash
# Check current quota
gcloud compute regions describe us-central1 \
  --project=accord-prod-project \
  --format="table(quotas.filter(metric:NVIDIA_L4_GPUS))"

# Request a quota increase via the Console
echo "https://console.cloud.google.com/iam-admin/quotas?project=accord-prod-project"
```

### KMS Key Permissions Error

**Symptom**: `terraform apply` fails with `PERMISSION_DENIED` when creating CMEK-encrypted resources.

**Cause**: The GCP service agent for the managed service (Firestore, Cloud Storage, or Compute Engine) does not have access to the KMS key. This often happens if the security module has not fully applied before the data or compute modules.

**Resolution**:

```bash
# Verify the KMS IAM bindings exist
gcloud kms keys get-iam-policy accord-prod-key \
  --keyring=accord-prod-keyring \
  --location=us-central1 \
  --project=accord-prod-project

# If bindings are missing, re-apply the security module first
terraform apply -target=module.security -var-file=environments/prod.tfvars \
  -var="project_id=accord-prod-project" \
  -var="domain=accord.yourdomain.com" \
  -var="alert_email=sre-team@yourdomain.com" \
  -var="container_image=us-central1-docker.pkg.dev/accord-prod-project/accord/tee-engine:v1.0.0"
```

### State Lock Not Released

**Symptom**: `terraform plan` hangs or errors with `Error locking state`.

**Cause**: A previous Terraform process was interrupted before releasing the lock.

**Resolution**:

```bash
# Identify the lock holder from the error message, then force-unlock
terraform force-unlock LOCK_ID
```

Only force-unlock if you have confirmed no other Terraform process is actively running.

### Health Check Failing After Deployment

**Symptom**: All instances marked unhealthy, load balancer returns 502.

**Cause**: The application startup takes longer than the auto-healing initial delay (600 seconds), or the health check endpoint path/port is misconfigured.

**Resolution**:

```bash
# Check instance startup logs
gcloud compute instances get-serial-port-output INSTANCE_NAME \
  --zone=us-central1-a \
  --project=accord-prod-project | tail -100

# SSH into the instance to debug
gcloud compute ssh INSTANCE_NAME \
  --zone=us-central1-a \
  --project=accord-prod-project \
  --tunnel-through-iap

# Inside the instance, check Docker and the health endpoint
sudo docker ps
sudo docker logs accord-tee --tail=50
curl -v http://localhost:8080/health
```

### Firestore Database Already Exists

**Symptom**: `terraform apply` fails with `ALREADY_EXISTS` for the Firestore database.

**Cause**: A Firestore database with the same name already exists in the project (possibly from a previous deployment or manual creation).

**Resolution**:

```bash
# Import the existing database into Terraform state
terraform import module.data.google_firestore_database.accord \
  "projects/accord-prod-project/databases/accord-prod"
```

### Audit Bucket Retention Policy Prevents Deletion

**Symptom**: `terraform destroy` fails on the audit logs bucket with a retention policy error.

**Cause**: The audit bucket has a locked retention policy (`is_locked = true`). This is by design for compliance. Objects cannot be deleted until their retention period expires.

**Resolution**: This is intentional. The audit bucket cannot be deleted while it contains objects within the retention window. To remove the bucket, all objects must age past the 7-year retention period. For non-production environments, consider using a shorter retention period by overriding `audit_retention_days`.

### Cloud Armor Blocking Legitimate Traffic

**Symptom**: Users receive 403 responses from the load balancer.

**Cause**: One of the OWASP WAF rules (SQLi, XSS, LFI, RFI, RCE) is matching legitimate request payloads.

**Resolution**:

```bash
# Identify which rule is triggering
gcloud logging read \
  'resource.type="http_load_balancer" AND jsonPayload.enforcedSecurityPolicy.outcome="DENY"' \
  --project=accord-prod-project \
  --limit=20 \
  --format="table(timestamp,jsonPayload.enforcedSecurityPolicy.name,jsonPayload.enforcedSecurityPolicy.matchedFieldType,httpRequest.requestUrl)"
```

If a specific rule is producing false positives, consider tuning the rule sensitivity or adding path-based exclusions in the Cloud Armor policy.

---

## Appendix A: Complete Output Reference

After a successful `terraform apply`, the following outputs are available:

```bash
terraform output                    # Show all outputs
terraform output load_balancer_ip   # Show a specific output
terraform output -json              # Machine-readable JSON format
```

| Output | Description |
|---|---|
| `vpc_id` | VPC resource ID |
| `vpc_self_link` | VPC self-link |
| `private_subnet_self_link` | Private subnet self-link |
| `cloud_nat_ip` | Cloud NAT egress IP address |
| `kms_keyring_id` | KMS keyring resource ID |
| `kms_crypto_key_id` | KMS crypto key resource ID |
| `vm_service_account_email` | VM service account email |
| `deploy_service_account_email` | Deploy service account email |
| `cloud_armor_policy_name` | Cloud Armor policy name |
| `firestore_database_name` | Firestore database name |
| `audit_logs_bucket_name` | Audit logs bucket name |
| `audit_logs_bucket_url` | Audit logs bucket URL |
| `documents_bucket_name` | Documents bucket name |
| `documents_bucket_url` | Documents bucket URL |
| `load_balancer_ip` | HTTPS load balancer external IP |
| `managed_instance_group_name` | MIG name |
| `ssl_certificate_name` | Managed SSL certificate name |
| `health_check_name` | Health check name |
| `log_sink_name` | Audit log sink name |
| `dashboard_name` | Monitoring dashboard name |
| `notification_channel_name` | Alert notification channel name |
| `dns_configuration` | DNS setup instructions |

---

## Appendix B: Compliance Evidence Collection

For SOC 2 Type II and ISO 27001 audits, use the following commands to collect evidence of controls in place:

```bash
PROJECT_ID="accord-prod-project"

# B.1 -- Encryption at rest: Verify CMEK key exists and rotation is configured
gcloud kms keys describe accord-prod-key \
  --keyring=accord-prod-keyring \
  --location=us-central1 \
  --project="${PROJECT_ID}" \
  --format="yaml(purpose,rotationPeriod,nextRotationTime,primary)"

# B.2 -- Encryption in transit: Verify SSL policy enforces TLS 1.2+
gcloud compute ssl-policies describe accord-prod-ssl-policy \
  --project="${PROJECT_ID}" \
  --format="yaml(minTlsVersion,profile)"

# B.3 -- Network segmentation: List all firewall rules
gcloud compute firewall-rules list \
  --project="${PROJECT_ID}" \
  --filter="network:accord-prod-vpc" \
  --format="table(name,direction,priority,sourceRanges,allowed)"

# B.4 -- Least-privilege IAM: Show VM service account bindings
gcloud projects get-iam-policy "${PROJECT_ID}" \
  --flatten="bindings[].members" \
  --filter="bindings.members:accord-prod-vm@" \
  --format="table(bindings.role,bindings.members)"

# B.5 -- Audit logging: Verify log sink is active
gcloud logging sinks describe accord-prod-audit-log-sink \
  --project="${PROJECT_ID}" \
  --format="yaml(destination,filter,writerIdentity)"

# B.6 -- Data retention: Verify bucket retention lock
gsutil retention get "gs://accord-prod-audit-logs-${PROJECT_ID}"

# B.7 -- WAF rules: List Cloud Armor policy rules
gcloud compute security-policies describe accord-prod-security-policy \
  --project="${PROJECT_ID}" \
  --format="table(rules.priority,rules.action,rules.description)"

# B.8 -- Confidential Computing: Verify instance template settings
gcloud compute instance-templates describe \
  $(gcloud compute instance-templates list \
    --project="${PROJECT_ID}" \
    --filter="name:accord-prod" \
    --format="value(name)" \
    --limit=1) \
  --project="${PROJECT_ID}" \
  --format="yaml(properties.confidentialInstanceConfig,properties.shieldedInstanceConfig)"

# B.9 -- Monitoring: List active alert policies
gcloud alpha monitoring policies list \
  --project="${PROJECT_ID}" \
  --filter="displayName:accord-prod" \
  --format="table(displayName,enabled,conditions.displayName)"
```

---

## Appendix C: Importing Existing Resources

If resources were created manually and need to be brought under Terraform management:

```bash
# Import a VPC
terraform import 'module.network.google_compute_network.vpc' \
  projects/PROJECT_ID/global/networks/accord-prod-vpc

# Import a Cloud KMS key
terraform import 'module.security.google_kms_crypto_key.accord' \
  projects/PROJECT_ID/locations/us-central1/keyRings/accord-prod-keyring/cryptoKeys/accord-prod-key

# Import a Firestore database
terraform import 'module.data.google_firestore_database.accord' \
  projects/PROJECT_ID/databases/accord-prod

# Import a Cloud Storage bucket
terraform import 'module.data.google_storage_bucket.audit_logs' \
  accord-prod-audit-logs-PROJECT_ID

# Import a service account
terraform import 'module.security.google_service_account.vm' \
  projects/PROJECT_ID/serviceAccounts/accord-prod-vm@PROJECT_ID.iam.gserviceaccount.com
```

After importing, run `terraform plan` to verify the imported state matches the HCL configuration and resolve any drift.
