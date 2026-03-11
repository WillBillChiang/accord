# Accord Confidential VM Operations Guide

## Overview

This guide covers the day-to-day operations of the GCP Confidential VM that runs the Accord negotiation engine. The Confidential VM is the most security-critical component of the system -- it contains all confidential negotiation data during active sessions. Its memory is hardware-encrypted by AMD SEV-SNP, ensuring that even the cloud provider cannot read its contents. Operations must be performed carefully to maintain security guarantees and minimize downtime.

## Building the Container Image

### Source Files

The application is built from the project root using the `Dockerfile`:

```
app/
  main.py                       # Entry point (FastAPI application)
  server.py                     # Server configuration and startup
  auth.py                       # Firebase Auth ID token verification middleware
  audit.py                      # Per-request audit logging middleware
  rate_limit.py                 # Sliding window rate limiter
  websocket_manager.py          # WebSocket connection management
  session.py                    # Session lifecycle management
  attestation.py                # GCE metadata attestation reporting
  kms_client.py                 # Cloud KMS client
  firestore_client.py           # Firestore client
  agent/
    base_agent.py               # LLM-powered negotiation agent
    buyer_agent.py              # Buyer-specific agent
    seller_agent.py             # Seller-specific agent
    preflight.py                # Hard constraint enforcement
    llm_engine.py               # LLM wrapper (GPU-accelerated)
  protocol/
    sao.py                      # SAO protocol engine
    zopa.py                     # ZOPA computation
    nash_bargaining.py          # Nash Bargaining Solution
    schemas.py                  # Pydantic data models
  crypto/
    session_keys.py             # Ephemeral AES-256-GCM key management
    secure_delete.py            # Cryptographic zeroing
  models/                       # (Model files directory, if bundled)
```

### Build Process

```bash
# Navigate to the project root
cd /path/to/accord

# Ensure the quantized LLM model is present (if bundled in image)
ls -la app/models/negotiator-7b-q4.gguf
# Should show the GGUF model file (typically 3-7 GB)

# Build the Docker image
docker build -t accord-app:latest .

# Verify the image
docker images accord-app
```

### Build Dependencies

The Dockerfile installs the following packages:

| Package | Version | Purpose |
|---------|---------|---------|
| Python 3.11 | System | Runtime |
| llama-cpp-python | 0.3.4+ | LLM inference (GPU-accelerated via CUDA) |
| pydantic | 2.10.x | Data validation and schemas |
| cryptography | 44.0.x | AES-256-GCM encryption |
| google-cloud-firestore | 2.x | Firestore client |
| google-cloud-kms | 2.x | Cloud KMS client |
| google-cloud-storage | 2.x | Cloud Storage client |
| firebase-admin | 6.x | Firebase Auth ID token verification |
| fastapi | 0.115.x | HTTP framework |
| uvicorn | Latest | ASGI server |
| scipy | 1.14.x | Numerical computations |

### Image Size Considerations

The container image may include the full LLM model, making it large (4-10 GB). Alternatively, the model can be downloaded from Cloud Storage at startup.

| Component | Typical Size |
|-----------|-------------|
| Base OS (Debian/Ubuntu minimal) | ~200 MB |
| Python + packages + CUDA runtime | ~2 GB |
| LLM model (7B Q4) | ~4 GB |
| Runtime overhead | ~1 GB |
| **Total recommended** | **6-8 GB** |

---

## Pushing to Artifact Registry

The container image is pushed to Google Artifact Registry for deployment to Confidential VMs.

```bash
# Set variables
PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
REPO="accord"
IMAGE_TAG="v1.0.0"

# Authenticate Docker with Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev"

# Tag the image
docker tag accord-app:latest \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app:${IMAGE_TAG}"

# Push to Artifact Registry
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app:${IMAGE_TAG}"
```

---

## Recording and Publishing Image Digests

The container image digest serves as the integrity measurement for attestation. It is the equivalent of PCR values in the previous Nitro Enclave architecture. The digest is a SHA-256 hash of the image manifest and is deterministic -- the same build inputs always produce the same digest.

### Recording

After each push, record the image digest:

```bash
# Get the digest from Artifact Registry
IMAGE_DIGEST=$(gcloud artifacts docker images describe \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app:${IMAGE_TAG}" \
  --format="value(image_summary.digest)")

echo "Image Digest: $IMAGE_DIGEST"

# Save to a version-controlled file
echo "$IMAGE_DIGEST" > IMAGE_DIGEST.txt
echo "Tag: ${IMAGE_TAG}" >> IMAGE_DIGEST.txt
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> IMAGE_DIGEST.txt
```

### Publishing

Image digests must be published so that negotiating parties can verify the deployment before submitting data. Recommended publication channels:

1. **Project repository** (version-controlled file, e.g., `IMAGE_DIGEST.txt`)
2. **API response** (via `GET /api/v1/attestation`)
3. **Company security page** (for public audits)

### Storing in Secret Manager

```bash
echo -n "$IMAGE_DIGEST" | gcloud secrets versions add accord-image-digest \
  --data-file=-

# Or create if it does not exist
echo -n "$IMAGE_DIGEST" | gcloud secrets create accord-image-digest \
  --data-file=- \
  --replication-policy="automatic"
```

---

## Deploying and Managing Confidential VMs

### Managed Instance Group (MIG)

The Confidential VM runs within a Managed Instance Group (MIG) that provides:
- Automatic instance recovery (autohealing) based on health checks
- Rolling updates for zero-downtime deployments
- Target size management

### Verifying Confidential VM Status

```bash
# List instances in the MIG
gcloud compute instance-groups managed list-instances \
  accord-prod-mig \
  --zone=us-central1-a

# Describe a specific instance to verify Confidential VM settings
INSTANCE_NAME="accord-prod-xxxx"  # From the list output
gcloud compute instances describe "$INSTANCE_NAME" \
  --zone=us-central1-a \
  --format="yaml(confidentialInstanceConfig,shieldedInstanceConfig,guestAccelerators)"
```

Expected output should show:
```yaml
confidentialInstanceConfig:
  enableConfidentialCompute: true
shieldedInstanceConfig:
  enableSecureBoot: true
  enableVtpm: true
  enableIntegrityMonitoring: true
guestAccelerators:
- acceleratorCount: 1
  acceleratorType: .../nvidia-l4
```

### Resource Allocation Guidelines

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| Machine Type | n2d-standard-4 | n2d-standard-8 | AMD EPYC required for SEV-SNP |
| GPU | 1x NVIDIA L4 | 1x NVIDIA H100 | For LLM inference |
| Boot Disk | 50 GB | 100 GB | SSD, encrypted with Cloud KMS |
| RAM | 16 GB | 32 GB | Must hold application + model + sessions |

### Stopping a Confidential VM

```bash
# Stop via MIG (graceful)
gcloud compute instance-groups managed resize \
  accord-prod-mig \
  --size=0 \
  --zone=us-central1-a
```

**Warning:** Stopping or terminating a Confidential VM immediately triggers AMD SEV-SNP key destruction, rendering all VM memory irrecoverable. This includes any active negotiation sessions. Ensure all sessions are completed or properly terminated via the API before stopping.

### Viewing Application Logs

```bash
# View logs from Cloud Logging
gcloud logging read \
  'resource.type="gce_instance" AND resource.labels.instance_id="<instance-id>"' \
  --limit=100 \
  --format="table(timestamp,textPayload)"

# Stream logs in real-time
gcloud logging tail \
  'resource.type="gce_instance" AND resource.labels.instance_id="<instance-id>"'

# Or via serial console (if enabled for debugging)
gcloud compute instances get-serial-port-output "$INSTANCE_NAME" \
  --zone=us-central1-a
```

**Note:** Serial console access should be disabled in production. If enabled temporarily for debugging, it is logged in Cloud Audit Logs.

---

## Updating the Application (Rolling Update Procedure)

When the application code changes (bug fix, model update, etc.), follow this procedure to update via a MIG rolling update:

### Pre-Update

1. **Drain active sessions**: Wait for all active negotiations to complete, or terminate them gracefully.

   ```bash
   # Check for active sessions via the API
   curl -H "Authorization: Bearer $TOKEN" \
     https://api.accord.example.com/api/v1/sessions
   ```

2. **Notify users**: If sessions must be terminated, notify the affected parties.

### Update Procedure

```bash
# 1. Build the new container image
docker build -t accord-app:v2 .

# 2. Tag and push to Artifact Registry
docker tag accord-app:v2 \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app:v2"

docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app:v2"

# 3. Record the NEW image digest
NEW_DIGEST=$(gcloud artifacts docker images describe \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app:v2" \
  --format="value(image_summary.digest)")

echo "New Image Digest: $NEW_DIGEST"

# 4. Update the Terraform variable and apply
terraform apply -var="container_image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/accord-app@${NEW_DIGEST}"

# 5. The MIG performs a rolling update automatically
# Monitor the update progress:
gcloud compute instance-groups managed describe \
  accord-prod-mig \
  --zone=us-central1-a \
  --format="yaml(status)"

# 6. Update published image digest
echo -n "$NEW_DIGEST" | gcloud secrets versions add accord-image-digest --data-file=-

# 7. Verify attestation
curl https://api.accord.example.com/api/v1/attestation
```

### Post-Update Verification

```bash
# Verify application health
curl https://api.accord.example.com/health

# Verify attestation returns new image digest
curl https://api.accord.example.com/api/v1/attestation | python3 -m json.tool

# Verify SEV-SNP is still active
gcloud compute instances describe "$(gcloud compute instance-groups managed list-instances \
  accord-prod-mig --zone=us-central1-a --format='value(instance)' --limit=1)" \
  --zone=us-central1-a \
  --format="value(confidentialInstanceConfig.enableConfidentialCompute)"
# Expected: True

# Run a test negotiation session
# (use the testing guide for end-to-end test procedure)
```

---

## Key Rotation Procedure

### Cloud KMS Key Rotation

The Accord Cloud KMS key has automatic key rotation enabled (annually). Google handles this transparently -- previously encrypted data can still be decrypted using the prior key version, and new encryptions use the latest key version.

To verify auto-rotation is enabled:

```bash
gcloud kms keys describe accord-key \
  --keyring=accord \
  --location=us-central1 \
  --format="yaml(rotationPeriod,nextRotationTime)"
```

### Session Key Rotation

Session keys are ephemeral -- a new AES-256-GCM key is generated for every negotiation session inside the Confidential VM and destroyed when the session ends. No manual rotation is needed.

---

## Monitoring Confidential VM Health

### Health Check Flow

The Cloud Load Balancer performs periodic health checks against the `/health` endpoint. The MIG uses these health checks for autohealing -- if the health check fails, the MIG automatically replaces the instance.

```bash
# Check application health
curl https://api.accord.example.com/health

# Check attestation (verifies application is running and SEV-SNP is active)
curl https://api.accord.example.com/api/v1/attestation
```

If the attestation endpoint returns a 503, the application is unreachable.

### Monitoring Commands

```bash
# Check MIG instance status
gcloud compute instance-groups managed list-instances \
  accord-prod-mig \
  --zone=us-central1-a

# Check Confidential VM properties
gcloud compute instances describe "$INSTANCE_NAME" \
  --zone=us-central1-a \
  --format="yaml(confidentialInstanceConfig,shieldedInstanceConfig,status)"

# Check Shielded VM integrity
gcloud compute instances get-shielded-identity "$INSTANCE_NAME" \
  --zone=us-central1-a

# View application logs
gcloud logging read \
  'resource.type="gce_instance" AND severity>=WARNING' \
  --limit=50 \
  --format="table(timestamp,severity,textPayload)"
```

### Cloud Monitoring Metrics to Monitor

| Metric | Source | Alert Threshold |
|--------|--------|----------------|
| API error rate (5xx) | Cloud Load Balancer | > 1% |
| API latency (p99) | Cloud Load Balancer | > 5 seconds |
| Health check failures | MIG autohealing | Any occurrence |
| Application errors | Cloud Logging | > 3 per hour |
| Rate limit hits | Cloud Armor metrics | Informational |
| Firestore latency | Firestore metrics | > 500ms |
| Cloud KMS decrypt failures | Cloud Audit Logs | Any occurrence (may indicate unauthorized access) |
| VM integrity validation failure | Shielded VM metrics | Any occurrence (may indicate tampering) |
| GPU utilization | Cloud Monitoring (GPU metrics) | < 10% (underutilized) or > 95% (overloaded) |

---

## Troubleshooting Common Issues

### Confidential VM Fails to Start

**Symptom:** MIG fails to create the instance.

**Common causes:**

| Cause | Fix |
|-------|-----|
| Quota exceeded | Request quota increase for Confidential VMs or GPUs in the target zone |
| Machine type not available | Use an N2D machine type (AMD EPYC, required for SEV-SNP) |
| GPU not available in zone | Try a different zone or GPU type |
| Confidential VM not supported | Verify the machine type supports Confidential Computing |
| Boot image incompatible | Use a supported OS image (Ubuntu 20.04+, Debian 11+, or Container-Optimized OS) |

### Cloud KMS Decryption Fails

**Symptom:** Onboarding fails with "KMS decrypt failed" error.

**Common causes:**

| Cause | Fix |
|-------|-----|
| Service account lacks Cloud KMS permission | Check IAM binding for `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the Confidential VM service account |
| Wrong KMS key used for encryption | Ensure client encrypts with the correct Accord Cloud KMS key |
| Key version disabled or destroyed | Check key version status in Cloud KMS |
| Network connectivity to KMS | Verify Private Google Access is enabled and firewall rules allow egress to `restricted.googleapis.com` |

### Application Not Responding

**Symptom:** API requests time out or return 502/503.

**Common causes:**

| Cause | Fix |
|-------|-----|
| Application crashed | Check Cloud Logging for error messages; MIG autohealing should replace the instance |
| Container failed to start | Check serial console output for startup errors |
| Health check misconfigured | Verify health check endpoint and port match the application |
| GPU driver issue | Verify NVIDIA drivers are installed and GPU is detected |
| Out of memory | Increase machine type or reduce model size |

### Confidential VM Out of Memory

**Symptom:** Application crashes during negotiation, especially during LLM inference.

**Fix:** Increase the machine type:

```bash
# Update the instance template in Terraform
# Change machine_type to a larger size (e.g., n2d-standard-16)
terraform apply -var="machine_type=n2d-standard-16"

# The MIG will perform a rolling update to the new machine type
```

---

## Disaster Recovery

### Confidential VM Crash Recovery

If the Confidential VM crashes:

1. Any active negotiation sessions are lost (data was in hardware-encrypted memory only). The AMD SEV-SNP key is destroyed, making all memory irrecoverable.
2. Firestore still contains session metadata with the last known status.
3. The MIG autohealing will automatically replace the crashed instance.
4. Mark affected sessions as `error` in Firestore.
5. Notify affected parties to create new sessions.

```bash
# Verify MIG is replacing the instance
gcloud compute instance-groups managed list-instances \
  accord-prod-mig \
  --zone=us-central1-a

# If autohealing is not working, manually recreate
gcloud compute instance-groups managed recreate-instances \
  accord-prod-mig \
  --instances="$INSTANCE_NAME" \
  --zone=us-central1-a
```

### Full Environment Recovery

For complete environment recovery:

1. Redeploy all infrastructure via Terraform:
   ```bash
   terraform apply
   ```
2. Firestore has Point-in-Time Recovery enabled -- restore to any point in the last 7 days.
3. Cloud Storage audit logs have Object Versioning -- they survive accidental deletion.
4. Push the container image to Artifact Registry (if repository was destroyed).
5. Verify MIG creates a new Confidential VM.
6. Update DNS records if needed.
7. Redeploy Firebase Hosting and verify Firebase Auth configuration.

### Backup Checklist

| Component | Backup Strategy | Recovery Point |
|-----------|----------------|----------------|
| Terraform modules | Git repository | Latest commit |
| Container image | Artifact Registry | Latest push |
| Image digests | Secret Manager + Git | Latest build |
| Firestore data | Point-in-Time Recovery (automatic) | Any point in last 7 days |
| Cloud Storage audit logs | Object Versioning | Any version |
| Application code | Git repository | Latest commit |
| LLM model | Cloud Storage bucket | Latest version |
| Environment config | Secret Manager | Current values |
| Firebase Auth config | Firebase Console | Current settings |
| Terraform state | GCS backend (versioned) | Latest apply |
