#!/bin/bash
# Accord — Run All Test Suites
# Runs app, engine, frontend, and infrastructure tests.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

FAILED=0
RESULTS=()

run_suite() {
    local name="$1"
    local dir="$2"
    local cmd="$3"

    echo ""
    echo "========================================"
    echo "  Running: $name"
    echo "========================================"

    cd "$PROJECT_ROOT/$dir"

    if eval "$cmd"; then
        RESULTS+=("PASS: $name")
    else
        RESULTS+=("FAIL: $name")
        FAILED=1
    fi
}

# App tests (merged parent-app + engine)
if [ -d "$PROJECT_ROOT/app/tests" ] && [ "$(ls -A "$PROJECT_ROOT/app/tests"/*.py 2>/dev/null)" ]; then
    run_suite "App Unit Tests" "app" \
        "python3 -m pytest tests/ -v --tb=short 2>&1 || (source venv/bin/activate 2>/dev/null && python3 -m pytest tests/ -v --tb=short)"
fi

# Frontend tests
if [ -f "$PROJECT_ROOT/frontend/package.json" ]; then
    run_suite "Frontend Tests" "frontend" \
        "npm test -- --watchAll=false --passWithNoTests 2>&1"
fi

# Terraform validation
if command -v terraform >/dev/null 2>&1 && [ -f "$PROJECT_ROOT/infrastructure/main.tf" ]; then
    run_suite "Terraform Validation" "infrastructure" \
        "terraform init -backend=false -input=false >/dev/null 2>&1 && terraform validate 2>&1"
fi

# Terraform lint (optional)
if command -v tflint >/dev/null 2>&1 && [ -f "$PROJECT_ROOT/infrastructure/main.tf" ]; then
    run_suite "Terraform Lint" "infrastructure" \
        "tflint 2>&1"
fi

# Summary
echo ""
echo "========================================"
echo "  Test Results Summary"
echo "========================================"
for result in "${RESULTS[@]}"; do
    echo "  $result"
done
echo "========================================"

exit $FAILED
