#!/bin/bash
# Accord — Local Development Setup
# Sets up the development environment for all components.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  Accord Development Setup"
echo "========================================"

# Step 1: Check prerequisites
echo ""
echo "[1/4] Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "ERROR: node required"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "ERROR: npm required"; exit 1; }

PYTHON_VERSION=$(python3 --version 2>&1)
NODE_VERSION=$(node --version 2>&1)
echo "  Python: $PYTHON_VERSION"
echo "  Node:   $NODE_VERSION"

# Check optional tools
if command -v gcloud >/dev/null 2>&1; then
    echo "  gcloud: $(gcloud --version 2>&1 | head -1)"
else
    echo "  gcloud: NOT INSTALLED (optional for local dev, required for deployment)"
fi

if command -v terraform >/dev/null 2>&1; then
    echo "  Terraform: $(terraform --version 2>&1 | head -1)"
else
    echo "  Terraform: NOT INSTALLED (optional for local dev, required for deployment)"
fi

# Step 2: Setup app Python environment
echo ""
echo "[2/4] Setting up app Python environment..."
cd "$PROJECT_ROOT/app"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt 2>/dev/null || \
    pip install fastapi uvicorn google-cloud-firestore google-cloud-kms \
    firebase-admin pydantic cryptography scipy httpx websockets
pip install pytest pytest-cov pytest-asyncio httpx
deactivate

# Step 3: Setup frontend
echo ""
echo "[3/4] Setting up frontend..."
cd "$PROJECT_ROOT/frontend"
npm install

# Step 4: Create .env files
echo ""
echo "[4/4] Creating environment files..."

if [ ! -f "$PROJECT_ROOT/frontend/.env.local" ]; then
    cat > "$PROJECT_ROOT/frontend/.env.local" << 'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_WS_URL=ws://localhost:8080
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=
NEXT_PUBLIC_FIREBASE_PROJECT_ID=
EOF
    echo "  Created frontend/.env.local"
fi

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "To start development:"
echo "  App:       cd app && source venv/bin/activate && uvicorn main:app --reload --port 8080"
echo "  Frontend:  cd frontend && npm run dev"
echo "  Tests:     ./scripts/run-tests.sh"
