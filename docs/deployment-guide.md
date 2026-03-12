# Accord Deployment Guide

## Prerequisites

### GCP Project Requirements

- A GCP project with billing enabled
- A user or service account with Owner or Editor role (for initial deployment)
- `gcloud` CLI installed and authenticated (`gcloud auth login && gcloud config set project <project-id>`)
- Sufficient quotas for:
  - Compute Engine: At least one `n2d-standard-8` or `a2-highgpu-1g` instance (Confidential VM + GPU capable)
  - Firestore: Native Mode database
  - Cloud KMS: 1 keyring with 1 symmetric key
  - Cloud Storage: 2 buckets

### Local Tools

| Tool | Version | Purpose |
|------|---------|---------|
| gcloud CLI | >= 450.x | GCP resource management |
| Terraform | >= 1.5.x | Infrastructure deployment |
| Docker | >= 20.x | Container image build |
| Firebase CLI | >= 13.x | Firebase Auth and Hosting deployment |
| Node.js | >= 18.x | Frontend build |
| Python | >= 3.11 | Application runtime |
| Git | >= 2.x | Source control |

### Required GCP APIs

Enable the following APIs before deployment:

```bash
gcloud services enable \
  compute.googleapis.com \
  cloudkms.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iap.googleapis.com \
  servicenetworking.googleapis.com \
  firebase.googleapis.com \
  identitytoolkit.googleapis.com \
  firebasehosting.googleapis.com
```

---

## Deployment Order

Terraform modules are deployed together via a root module. The dependency graph is managed by Terraform automatically:

```
1. Network    (VPC, subnets, firewall rules, Cloud NAT, Private Google Access)
       |
2. Security   (Cloud KMS key, service accounts, Cloud Armor policy)
       |
3. Data       (Firestore database, Cloud Storage buckets)
       |
4. Compute    (Confidential VM instance template, MIG, Load Balancer)
       |
5. Monitoring (Cloud Monitoring dashboards, alerting, log sinks)
       |
6. Firebase   (Firebase Auth, Firebase Hosting -- deployed via Firebase CLI)
```

---

## Step 1: Initialize Terraform

### Configure the GCS Backend for State

Create a GCS bucket for Terraform state:

```bash
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"

gsutil mb -l "$REGION" "gs://${PROJECT_ID}-terraform-state"

gsutil versioning set on "gs://${PROJECT_ID}-terraform-state"
```

### Initialize Terraform

```bash
cd infrastructure/

# Create backend configuration
cat > backend.tf <<EOF
terraform {
  backend "gcs" {
    bucket = "${PROJECT_ID}-terraform-state"
    prefix = "accord/prod"
  }
}
EOF

terraform init
```

---

## Step 2: Configure Terraform Variables

Create a `terraform.tfvars` file:

```hcl
# infrastructure/terraform.tfvars

project_id    = "your-gcp-project-id"
region        = "us-central1"
environment   = "prod"

# Network
vpc_cidr          = "10.0.0.0/16"
public_subnet     = "10.0.1.0/24"
private_subnet    = "10.0.10.0/24"

# Compute
machine_type       = "n2d-standard-8"      # AMD EPYC (required for SEV-SNP)
gpu_type           = "nvidia-l4"            # or "nvidia-h100-80gb"
gpu_count          = 1
confidential_vm    = true
boot_disk_size_gb  = 100

# Cloud Armor
rate_limit_threshold = 2000
rate_limit_interval  = 300

# DNS (optional for non-prod -- omit for HTTP-only access via LB IP)
domain_name     = "accord.example.com"
api_domain      = "api.accord.example.com"
app_domain      = "app.accord.example.com"
```

---

## Step 3: Deploy Infrastructure with Terraform

### Plan

```bash
terraform plan -out=tfplan
```

Review the plan carefully. It should create:
- VPC with public and private subnets
- Firewall rules (ingress from LB, egress to Google APIs only)
- Cloud NAT and Cloud Router
- Cloud KMS keyring and symmetric key
- Service accounts with appropriate IAM bindings
- Cloud Armor security policy
- Firestore database (Native Mode)
- Cloud Storage buckets (audit logs, documents)
- Confidential VM instance template (SEV-SNP enabled, GPU attached)
- Managed Instance Group (MIG)
- HTTPS Cloud Load Balancer with Cloud Armor
- Cloud Monitoring dashboards and alerting policies
- Cloud Audit Logs sink

### Apply

```bash
terraform apply tfplan
```

**Verify:**

```bash
# Check all resources
terraform output

# Verify Confidential VM is running with SEV-SNP
gcloud compute instances list --filter="name~accord"
gcloud compute instances describe $(terraform output -raw instance_name) \
  --zone=$(terraform output -raw zone) \
  --format="yaml(confidentialInstanceConfig,shieldedInstanceConfig)"
```

Expected output should show:
- `confidentialInstanceConfig.enableConfidentialCompute: true`
- `shieldedInstanceConfig.enableSecureBoot: true`
- `shieldedInstanceConfig.enableVtpm: true`
- `shieldedInstanceConfig.enableIntegrityMonitoring: true`

---

## Step 4: Build and Push Container Image

### Create Artifact Registry Repository

```bash
gcloud artifacts repositories create accord \
  --repository-format=docker \
  --location="$REGION" \
  --description="Accord container images"
```

### Build and Push

```bash
# Configure Docker authentication for Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev"

# Build the container image
docker build -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest" \
  -f Dockerfile .

# Push to Artifact Registry
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest"
```

---

## Step 5: Record Image Digest

The container image digest serves as the integrity measurement for the Confidential VM deployment (analogous to PCR values in the previous Nitro Enclave architecture).

```bash
# Get the image digest
IMAGE_DIGEST=$(gcloud artifacts docker images describe \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest" \
  --format="value(image_summary.digest)")

echo "Image Digest: $IMAGE_DIGEST"
```

**Record this digest.** It is published for parties to verify that the deployed application matches the auditable source code. Store it in version control and publish it on the project security page.

```bash
# Store in Secret Manager for reference
echo -n "$IMAGE_DIGEST" | gcloud secrets create accord-image-digest \
  --data-file=- \
  --replication-policy="automatic"
```

---

## Step 6: Deploy Backend (Rolling Update via MIG)

Update the instance template to use the new container image, then trigger a rolling update:

```bash
# Update the Terraform variable with the new image digest
# (or update the instance template directly)

# Option A: Via Terraform
terraform apply -var="container_image=${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app@${IMAGE_DIGEST}"

# Option B: Manual MIG rolling update
gcloud compute instance-groups managed rolling-action restart \
  $(terraform output -raw mig_name) \
  --zone=$(terraform output -raw zone)
```

Verify the new instance is running:

```bash
gcloud compute instance-groups managed list-instances \
  $(terraform output -raw mig_name) \
  --zone=$(terraform output -raw zone)
```

---

## Step 7: Set Up Firebase Project

### Initialize Firebase

```bash
# Install Firebase CLI if not already installed
npm install -g firebase-tools

# Login to Firebase
firebase login

# Add Firebase to your GCP project
firebase projects:addfirebase "$PROJECT_ID"

# Initialize Firebase in the project directory
cd frontend/
firebase init
# Select: Hosting, Authentication
# Use existing project: your-gcp-project-id
```

---

## Step 8: Configure Firebase Auth

### Enable Email/Password Authentication

```bash
# Via Firebase Console: Authentication > Sign-in method > Email/Password > Enable
# Or via the Firebase Admin SDK / REST API

# Enable TOTP MFA via Firebase Console:
# Authentication > Sign-in method > Multi-factor authentication > Enable > TOTP
```

### Configure Auth Settings

In the Firebase Console (Authentication > Settings):

| Setting | Value | Rationale |
|---------|-------|-----------|
| Email/Password | Enabled | Primary sign-in method |
| Email enumeration protection | Enabled | Prevents email discovery attacks |
| MFA | Required (TOTP) | SOC 2 / ISO 27001 compliance |
| Password policy | Min 12 chars, upper + lower + number + symbol | Strong password requirement |

### Create the First Admin User

```bash
# Using Firebase Admin SDK (from a local script or Cloud Shell)
python3 -c "
import firebase_admin
from firebase_admin import auth as firebase_auth

firebase_admin.initialize_app()

user = firebase_auth.create_user(
    email='admin@example.com',
    password='TempP@ssw0rd123!',
    email_verified=True
)

firebase_auth.set_custom_user_claims(user.uid, {'admin': True})
print(f'Created admin user: {user.uid}')
"
```

---

## Step 9: Deploy Frontend to Firebase Hosting

### Configure Firebase Hosting

Create or update `firebase.json` in the frontend directory:

```json
{
  "hosting": {
    "public": "out",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ],
    "headers": [
      {
        "source": "**",
        "headers": [
          { "key": "X-Frame-Options", "value": "DENY" },
          { "key": "X-Content-Type-Options", "value": "nosniff" },
          { "key": "Referrer-Policy", "value": "strict-origin-when-cross-origin" },
          { "key": "Permissions-Policy", "value": "camera=(), microphone=(), geolocation=()" }
        ]
      }
    ]
  }
}
```

### Build and Deploy

```bash
cd frontend/

# Set environment variables
cat > .env.production <<EOF
NEXT_PUBLIC_API_URL=https://api.accord.example.com
NEXT_PUBLIC_WS_URL=wss://api.accord.example.com
NEXT_PUBLIC_FIREBASE_API_KEY=<firebase-api-key>
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=<project-id>.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=<project-id>
EOF

# Build the frontend
npm run build

# Deploy to Firebase Hosting
firebase deploy --only hosting
```

---

## Step 10: Configure DNS and SSL

### API Domain (Cloud Load Balancer)

1. Reserve a global static IP address (created by Terraform).
2. Create a DNS A record for `api.accord.example.com` pointing to the load balancer IP.
3. The Cloud Load Balancer automatically provisions a Google-managed SSL certificate.

```bash
# Get the load balancer IP
LB_IP=$(terraform output -raw load_balancer_ip)
echo "Create DNS A record: api.accord.example.com -> $LB_IP"
```

### Frontend Domain (Firebase Hosting)

1. In Firebase Console, go to Hosting > Custom Domains.
2. Add `app.accord.example.com`.
3. Follow Firebase instructions to create DNS records (TXT for verification, A/AAAA for routing).
4. Firebase automatically provisions and renews SSL certificates.

---

## Step 11: Environment Variable Configuration

### Backend Environment Variables

Set via the Confidential VM instance template metadata or a mounted Secret Manager volume:

| Variable | Description | Example |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | GCP project ID | `accord-prod` |
| `GCP_REGION` | GCP region | `us-central1` |
| `FIRESTORE_DATABASE` | Firestore database name | `(default)` |
| `KMS_KEY_NAME` | Cloud KMS key resource name | `projects/accord-prod/locations/us-central1/keyRings/accord/cryptoKeys/accord-key` |
| `FIREBASE_PROJECT_ID` | Firebase project ID | `accord-prod` |
| `CLOUD_STORAGE_AUDIT_BUCKET` | Audit logs bucket | `accord-prod-audit-logs` |
| `CLOUD_STORAGE_DOCS_BUCKET` | Documents bucket | `accord-prod-documents` |

### Frontend Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL | `https://api.accord.example.com` |
| `NEXT_PUBLIC_WS_URL` | WebSocket base URL | `wss://api.accord.example.com` |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase API key | `AIza...` |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain | `accord-prod.firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID | `accord-prod` |

---

## Post-Deployment Verification Checklist

### Infrastructure

- [ ] VPC created with correct CIDR blocks
- [ ] Private subnet with Private Google Access enabled
- [ ] VPC firewall rules: ingress from LB, egress to Google APIs only, deny all other egress
- [ ] VPC Flow Logs enabled
- [ ] Cloud NAT operational
- [ ] Cloud Router configured

### Security

- [ ] Cloud KMS keyring and key created
- [ ] Cloud KMS key rotation enabled (automatic, annual)
- [ ] Cloud KMS IAM binding restricts decrypt to Confidential VM service account
- [ ] Service accounts follow least privilege
- [ ] Cloud Armor security policy associated with Load Balancer backend
- [ ] Cloud Armor rules active (rate limiting, OWASP top 10, IP reputation)

### Authentication

- [ ] Firebase Auth configured with email/password + TOTP MFA
- [ ] Admin user created with admin custom claim
- [ ] Admin can sign in and complete MFA setup
- [ ] ID token issuance and verification works

### Data

- [ ] Firestore database created in Native Mode with encryption
- [ ] Cloud Storage buckets created with encryption and uniform bucket-level access
- [ ] Cloud Storage audit bucket has Object Versioning enabled
- [ ] Cloud Storage retention policies configured on audit bucket

### Compute

- [ ] Confidential VM running in private subnet with SEV-SNP enabled
- [ ] GPU attached and operational
- [ ] Shielded VM features enabled (Secure Boot, vTPM, Integrity Monitoring)
- [ ] Container image pulled and running
- [ ] Image digest recorded and published
- [ ] MIG health checks passing
- [ ] Application responding on expected port

### API Verification

```bash
# Health check
curl https://api.accord.example.com/health
# Expected: {"status":"healthy","service":"accord"}

# Attestation (no auth required)
curl https://api.accord.example.com/api/v1/attestation
# Expected: {"image_digest":"sha256:...","sev_snp_enabled":true,"secure_boot":true,"vm_id":"...","timestamp":...}

# Authenticated request
TOKEN=$(firebase auth:export --format=json | ...)  # Or get token via Firebase SDK
curl -H "Authorization: Bearer $TOKEN" https://api.accord.example.com/api/v1/sessions
# Expected: {"sessions":[]}
```

### Frontend

- [ ] Firebase Hosting deployment succeeded
- [ ] Frontend accessible at custom domain
- [ ] Sign-in flow works (email + password + TOTP)
- [ ] Session creation works through UI
- [ ] Attestation verification works through UI

### Monitoring

- [ ] Cloud Logging receiving application logs
- [ ] Cloud Audit Logs capturing admin activity and data access
- [ ] Cloud Monitoring dashboards showing metrics
- [ ] Alerting policies configured and tested
- [ ] Audit log entries being written to Firestore
