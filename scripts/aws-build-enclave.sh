#!/bin/bash
# Accord — Build Enclave Image
# Builds the Docker image and converts it to a Nitro Enclave Image File (EIF).
# Records PCR measurements for attestation verification.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENCLAVE_DIR="$PROJECT_ROOT/enclave"
OUTPUT_DIR="$PROJECT_ROOT/build"
IMAGE_NAME="accord-negotiation-enclave"
EIF_NAME="accord-enclave.eif"
PCR_FILE="$OUTPUT_DIR/pcr-values.json"

echo "========================================"
echo "  Accord Enclave Image Builder"
echo "========================================"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Step 1: Build Docker image
echo ""
echo "[1/4] Building Docker image..."
docker build \
    -t "$IMAGE_NAME:latest" \
    -f "$ENCLAVE_DIR/Dockerfile.enclave" \
    "$ENCLAVE_DIR"

echo "Docker image built: $IMAGE_NAME:latest"

# Step 2: Convert to Nitro Enclave Image File
echo ""
echo "[2/4] Converting to Enclave Image File (EIF)..."
nitro-cli build-enclave \
    --docker-uri "$IMAGE_NAME:latest" \
    --output-file "$OUTPUT_DIR/$EIF_NAME" \
    2>&1 | tee "$OUTPUT_DIR/build-output.log"

echo "EIF created: $OUTPUT_DIR/$EIF_NAME"

# Step 3: Extract and save PCR values
echo ""
echo "[3/4] Extracting PCR measurements..."
PCR_OUTPUT=$(nitro-cli build-enclave \
    --docker-uri "$IMAGE_NAME:latest" \
    --output-file /dev/null 2>&1 || true)

# Parse PCR values from build output
python3 -c "
import json, re, sys

with open('$OUTPUT_DIR/build-output.log', 'r') as f:
    content = f.read()

# Find the JSON measurements block
match = re.search(r'\{[^}]*Measurements[^}]*\{[^}]*\}[^}]*\}', content, re.DOTALL)
if match:
    measurements = json.loads(match.group())
    pcr_values = {
        'PCR0': measurements.get('Measurements', {}).get('PCR0', ''),
        'PCR1': measurements.get('Measurements', {}).get('PCR1', ''),
        'PCR2': measurements.get('Measurements', {}).get('PCR2', ''),
        'build_timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
        'image_name': '$IMAGE_NAME',
    }
    with open('$PCR_FILE', 'w') as f:
        json.dump(pcr_values, f, indent=2)
    print(json.dumps(pcr_values, indent=2))
else:
    print('WARNING: Could not extract PCR values from build output', file=sys.stderr)
    print('Check $OUTPUT_DIR/build-output.log for details', file=sys.stderr)
" 2>/dev/null || echo "PCR extraction requires Python 3"

# Step 4: Summary
echo ""
echo "[4/4] Build complete!"
echo "========================================"
echo "  EIF:  $OUTPUT_DIR/$EIF_NAME"
echo "  PCRs: $PCR_FILE"
echo "========================================"
echo ""
echo "IMPORTANT: Publish the PCR values so both parties can verify"
echo "the enclave before submitting their confidential data."
echo ""
echo "To run the enclave:"
echo "  nitro-cli run-enclave \\"
echo "    --eif-path $OUTPUT_DIR/$EIF_NAME \\"
echo "    --cpu-count 40 \\"
echo "    --memory 81920 \\"
echo "    --enclave-cid 16"
