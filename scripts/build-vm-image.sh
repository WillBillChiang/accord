#!/bin/bash
# Accord — Build and Push Container Image
# Builds the Docker container image for the GCP Confidential VM
# and pushes it to Artifact Registry. Records the image digest
# (equivalent of PCR values) for attestation verification.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
APP_DIR="$PROJECT_ROOT/app"
OUTPUT_DIR="$PROJECT_ROOT/build"

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
REPO="accord"
IMAGE_NAME="accord-app"
VERSION="${VERSION:-$(date +%Y%m%d-%H%M%S)}"
FULL_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}"
DIGEST_FILE="$OUTPUT_DIR/image-digest.json"

echo "========================================"
echo "  Accord Container Image Builder"
echo "========================================"
echo "  Project:  $PROJECT_ID"
echo "  Region:   $REGION"
echo "  Image:    $FULL_IMAGE:$VERSION"
echo "========================================"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Step 1: Ensure Artifact Registry repo exists
echo ""
echo "[1/4] Ensuring Artifact Registry repository..."
gcloud artifacts repositories describe "$REPO" \
    --location="$REGION" \
    --project="$PROJECT_ID" >/dev/null 2>&1 || \
gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --description="Accord Negotiation Engine container images"

echo "  Repository: ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# Step 2: Build the Docker image
echo ""
echo "[2/4] Building Docker image..."
docker build \
    -t "${FULL_IMAGE}:${VERSION}" \
    -t "${FULL_IMAGE}:latest" \
    -f "$APP_DIR/Dockerfile" \
    "$APP_DIR"

echo "  Docker image built: ${FULL_IMAGE}:${VERSION}"

# Step 3: Push to Artifact Registry
echo ""
echo "[3/4] Pushing to Artifact Registry..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker push "${FULL_IMAGE}:${VERSION}"
docker push "${FULL_IMAGE}:latest"

echo "  Image pushed successfully"

# Step 4: Record image digest
echo ""
echo "[4/4] Recording image digest..."
DIGEST=$(gcloud artifacts docker images describe \
    "${FULL_IMAGE}:${VERSION}" \
    --format='value(image_summary.digest)' \
    --project="$PROJECT_ID" 2>/dev/null || \
    docker inspect --format='{{index .RepoDigests 0}}' "${FULL_IMAGE}:${VERSION}" 2>/dev/null | cut -d@ -f2)

python3 -c "
import json
digest_info = {
    'image': '${FULL_IMAGE}',
    'version': '${VERSION}',
    'digest': '${DIGEST}',
    'build_timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'project_id': '${PROJECT_ID}',
    'region': '${REGION}',
}
with open('${DIGEST_FILE}', 'w') as f:
    json.dump(digest_info, f, indent=2)
print(json.dumps(digest_info, indent=2))
"

echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo "  Image:   ${FULL_IMAGE}:${VERSION}"
echo "  Digest:  ${DIGEST}"
echo "  Saved:   ${DIGEST_FILE}"
echo "========================================"
echo ""
echo "IMPORTANT: Publish the image digest so both parties can verify"
echo "the Confidential VM before submitting their confidential data."
echo ""
echo "To deploy:"
echo "  cd infrastructure && terraform apply -var container_image=${FULL_IMAGE}:${VERSION}"
