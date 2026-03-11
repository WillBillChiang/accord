# Accord GCP Deployment Quick Start

A simple, step-by-step guide to deploy Accord on Google Cloud.

---

## Prerequisites

- GCP project with billing enabled
- `gcloud`, `terraform`, `docker`, `firebase-tools`, `node` installed
- Authenticated: `gcloud auth login && gcloud config set project YOUR_PROJECT_ID`

## 1. Enable Required APIs

```bash
gcloud services enable \
  compute.googleapis.com cloudkms.googleapis.com firestore.googleapis.com \
  storage.googleapis.com logging.googleapis.com monitoring.googleapis.com \
  artifactregistry.googleapis.com iam.googleapis.com firebase.googleapis.com \
  identitytoolkit.googleapis.com firebasehosting.googleapis.com \
  artifactregistry.googleapis.com
```

## 2. Deploy Infrastructure

```bash
cd infrastructure/

# Edit variables for your project
cp environments/prod.tfvars terraform.tfvars
# Edit terraform.tfvars: set project_id, region, domain_name, etc.

terraform init
terraform plan
terraform apply
```

This creates: VPC, Confidential VM (AMD SEV-SNP + GPU), Cloud KMS, Firestore, Cloud Storage, Load Balancer, Cloud Armor, and monitoring.

## 3. Build and Deploy the Backend

```bash
cd app/

# Build container image with GPU support
PROJECT_ID=$(gcloud config get-value project)
REGION=$(gcloud config get-value compute/region)

gcloud artifacts repositories create accord \
  --repository-format=docker --location="$REGION"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"

docker build -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest" .
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest"

# Record image digest (the integrity measurement for attestation)
gcloud artifacts docker images describe \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest" \
  --format="value(image_summary.digest)"
```

Then trigger a rolling update on the Managed Instance Group:

```bash
cd ../infrastructure/
terraform apply -var="container_image=${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:latest"
```

## 4. Set Up Firebase Auth

```bash
# Add Firebase to your GCP project
firebase projects:addfirebase "$PROJECT_ID"

# In Firebase Console (console.firebase.google.com):
# 1. Authentication > Sign-in method > Enable Email/Password
# 2. Authentication > Sign-in method > Multi-factor auth > Enable TOTP
# 3. Create first admin user (see below)
```

Create the admin user:

```bash
python3 -c "
import firebase_admin
from firebase_admin import auth
firebase_admin.initialize_app()
user = auth.create_user(email='admin@yourcompany.com', password='CHANGE_ME_NOW!', email_verified=True)
auth.set_custom_user_claims(user.uid, {'admin': True})
print(f'Admin user created: {user.uid}')
"
```

## 5. Deploy Frontend

```bash
cd frontend/

# Set environment variables
cat > .env.production <<EOF
NEXT_PUBLIC_API_URL=https://api.your-domain.com
NEXT_PUBLIC_WS_URL=wss://api.your-domain.com
NEXT_PUBLIC_FIREBASE_API_KEY=your-firebase-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
EOF

npm install
npm run build
firebase deploy --only hosting
```

## 6. Configure DNS

Point your domain to the load balancer IP:

```bash
LB_IP=$(cd ../infrastructure && terraform output -raw load_balancer_ip)
echo "Create DNS A record: api.your-domain.com -> $LB_IP"
```

For the frontend, add a custom domain in Firebase Console > Hosting.

## 7. Verify

```bash
# Health check
curl https://api.your-domain.com/health

# Attestation (public endpoint — verifies TEE is active)
curl https://api.your-domain.com/api/v1/attestation

# Should return: sev_snp_enabled: true, secure_boot: true, image_digest: sha256:...
```

---

## Project Structure

```
accord/
  app/                    # GCP backend (Confidential VM)
    main.py               # FastAPI application
    engine/               # Negotiation engine (LLM + protocols)
    middleware/            # Auth (Firebase), audit, rate limiting
    models/               # Firestore data layer
    routes/               # API endpoints
    Dockerfile            # CUDA-enabled container
    tests/                # All tests
  frontend/               # Next.js 15 + Firebase Auth
  infrastructure/         # Terraform (GCP)
    modules/              # network, security, data, compute, monitoring
    aws/                  # Legacy AWS CloudFormation (archived)
  scripts/                # Build and deployment scripts
  docs/                   # Documentation
  aws-app/                # Legacy AWS parent-app (archived)
  aws-enclave/            # Legacy AWS Nitro Enclave code (archived)
```

## Hackathon / Development Setup

For hackathons, demos, or short-lived deployments, use the cost-optimized configuration:

```bash
cd infrastructure/
cp environments/hackathon.tfvars terraform.tfvars
# Edit terraform.tfvars: set project_id, domain, alert_email, container_image

terraform init
terraform plan
terraform apply
```

This uses **Spot VMs** (~60-70% cheaper) and a smaller machine type (`g2-standard-8`) while keeping the full TEE (AMD SEV-SNP) and GPU (NVIDIA L4) inference pipeline intact.

**Estimated costs:**

| Duration | Cost |
|----------|------|
| 3-day hackathon | ~$21-24 |
| 1 week | ~$50-60 |
| 1 month | ~$210-240 |

> **Note:** Spot VMs may be preempted by GCP with short notice. This is acceptable for hackathons but not for production. The VM will automatically restart when capacity becomes available.

To switch back to production settings, use `environments/prod.tfvars` instead.

---

## Updating the Application

```bash
# 1. Make code changes
# 2. Run tests
cd app && source .venv/bin/activate && pytest tests/

# 3. Build and push new image
docker build -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:v2" app/
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:v2"

# 4. Rolling update
cd infrastructure && terraform apply -var="container_image=...accord-app:v2"
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| GPU not detected | Verify `nvidia-smi` works inside the VM; check machine type supports GPUs |
| SEV-SNP not enabled | Must use `n2d-*` or `c3d-*` machine types (AMD EPYC) |
| Firebase Auth 401 | Check `FIREBASE_PROJECT_ID` env var is set on the backend |
| MFA required error | User must enroll TOTP MFA before accessing protected endpoints |
| Firestore permission denied | Check service account IAM bindings |
| LLM out of memory | Increase GPU type (L4 -> H100) or reduce model context size |
