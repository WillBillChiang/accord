# Accord Testing Guide

## Overview

Accord uses a multi-layered testing strategy covering the negotiation engine, API application, frontend web interface, end-to-end workflows, and infrastructure modules. This guide explains how to set up, run, and interpret each test suite.

## Test Suite Summary

| Suite | Tool | Directory | What It Tests |
|-------|------|-----------|---------------|
| Engine Tests | pytest | `app/tests/` | Negotiation protocol, agents, preflight, crypto, ZOPA, Nash |
| API Tests | pytest | `app/tests/` | API routes, middleware, Firestore client, auth middleware |
| Frontend Tests | Jest + React Testing Library | `frontend/` | React components, hooks, API integration, UI interactions |
| E2E Tests | Playwright | `frontend/` (or `tests/e2e/`) | Full user journeys through the web interface |
| Infrastructure Tests | terraform validate + tflint + tfsec | `infrastructure/` | Terraform module validity, best practices, and security |

## Test Coverage Targets

| Component | Line Coverage Target | Branch Coverage Target |
|-----------|---------------------|----------------------|
| Engine (`app/`) | 90% | 85% |
| API (`app/`) | 85% | 80% |
| Frontend (`frontend/`) | 80% | 75% |
| Overall | 85% | 80% |

---

## Engine Tests (pytest)

### What They Cover

The engine test suite validates the core negotiation logic. Since the Confidential VM provides hardware-level memory encryption (AMD SEV-SNP), the application code itself runs as standard Python. Tests mock GCP-specific interfaces (GCE metadata service for attestation, Cloud KMS for decryption).

| Test Area | Description |
|-----------|-------------|
| **SAO Protocol** | Full negotiation flow, round progression, deal/no-deal outcomes, Nash fallback |
| **ZOPA Computation** | ZOPA existence check, edge cases, input validation |
| **Nash Bargaining** | Price computation, outside option, reservation clamping, boundary conditions |
| **Preflight Checks** | Budget cap enforcement, concession rate limiting, disclosure boundary blocking, round limits |
| **Agent Logic** | Proposal generation, evaluation, acceptance thresholds, fallback strategy |
| **LLM Engine** | JSON generation, error handling, unavailability fallback |
| **Session Management** | Lifecycle transitions, onboarding, expiry, termination, provable deletion |
| **Crypto** | Session key generation/encryption/decryption/destruction, secure zeroing |
| **Attestation** | GCE metadata parsing, attestation response generation, mock metadata service |
| **Cloud KMS Client** | Encrypt/decrypt operations, error handling |
| **Schemas** | Pydantic model validation, field constraints, serialization |

### Setup

```bash
cd /path/to/accord/app

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install pydantic==2.10.* cryptography==44.0.* scipy==1.14.*

# Install GCP client libraries
pip install google-cloud-firestore google-cloud-kms google-cloud-storage firebase-admin

# Install test dependencies
pip install pytest pytest-cov pytest-asyncio pytest-mock

# Note: llama-cpp-python is NOT required for testing.
# The LLM engine gracefully handles its absence.
```

### Running Tests

```bash
# Run all engine tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

# Run a specific test file
pytest tests/test_sao.py -v

# Run a specific test
pytest tests/test_preflight.py::test_budget_cap_buyer_clamped -v

# Run tests matching a pattern
pytest tests/ -v -k "nash"

# Run with detailed failure output
pytest tests/ -v --tb=long
```

### Key Test Examples

**SAO Protocol Test:**

```python
def test_sao_deal_reached():
    """Verify SAO produces a deal when ZOPA exists and prices converge."""
    seller_config = PartyConfig(
        role=NegotiationRole.SELLER,
        budget_cap=3_000_000,
        reservation_price=3_500_000,
        max_rounds=10,
    )
    buyer_config = PartyConfig(
        role=NegotiationRole.BUYER,
        budget_cap=5_000_000,
        reservation_price=4_500_000,
        max_rounds=10,
    )
    session = NegotiationSession(session_id="test-1", max_duration_sec=3600)
    session.onboard_party(seller_config)
    session.onboard_party(buyer_config)

    seller_agent = SellerAgent(seller_config, LLMEngine.__new__(LLMEngine))
    buyer_agent = BuyerAgent(buyer_config, LLMEngine.__new__(LLMEngine))

    protocol = SAOProtocol(seller_agent, buyer_agent, session)
    outcome = protocol.run()

    assert outcome.outcome in ("deal_reached", "no_agreement")
    assert outcome.rounds_completed > 0
```

**Preflight Test:**

```python
def test_never_disclose_blocked():
    """Verify NEVER_DISCLOSE fields are blocked by preflight."""
    config = PartyConfig(
        role=NegotiationRole.SELLER,
        budget_cap=1_000_000,
        reservation_price=1_200_000,
        disclosure_fields={"secret_field": DisclosureTier.NEVER_DISCLOSE},
    )
    proposal = Proposal(
        round_number=1,
        from_party="test-party",
        price=1_500_000,
        disclosed_fields={"secret_field": "should be blocked"},
    )

    with pytest.raises(PreflightViolation) as exc_info:
        preflight_check(proposal, config, [])

    assert exc_info.value.constraint == "DISCLOSURE_BOUNDARY"
```

**Secure Deletion Test:**

```python
def test_session_data_destroyed():
    """Verify all session data is zeroed on termination."""
    session = NegotiationSession(session_id="test-del", max_duration_sec=3600)
    config = PartyConfig(
        role=NegotiationRole.SELLER,
        budget_cap=1_000_000,
        reservation_price=1_200_000,
        confidential_data={"secret": "very_private_value"},
    )
    session.onboard_party(config)
    session.terminate("test")

    assert session.seller_config is None
    assert session.buyer_config is None
    assert len(session.negotiation_log) == 0
    assert session.key_manager.is_destroyed
```

### Mocking GCP Services

**Mocking GCE Metadata for Attestation:**

```python
from unittest.mock import patch, MagicMock

@patch("attestation.requests.get")
def test_attestation_report(mock_get):
    """Verify attestation report generation from GCE metadata."""
    # Mock GCE metadata responses
    mock_responses = {
        "http://metadata.google.internal/computeMetadata/v1/instance/id": "12345",
        "http://metadata.google.internal/computeMetadata/v1/instance/attributes/container-image-digest": "sha256:abc123...",
    }

    def side_effect(url, **kwargs):
        response = MagicMock()
        response.text = mock_responses.get(url, "")
        response.status_code = 200
        return response

    mock_get.side_effect = side_effect

    report = generate_attestation_report()
    assert report["vm_id"] == "12345"
    assert report["image_digest"] == "sha256:abc123..."
    assert report["sev_snp_enabled"] is True  # or mock accordingly
```

**Mocking Cloud KMS:**

```python
from unittest.mock import patch, MagicMock

@patch("kms_client.kms.KeyManagementServiceClient")
def test_kms_decrypt(mock_kms_class):
    """Verify Cloud KMS decryption."""
    mock_client = MagicMock()
    mock_kms_class.return_value = mock_client

    mock_client.decrypt.return_value = MagicMock(
        plaintext=b'{"role": "buyer", "budget_cap": 5000000}'
    )

    result = decrypt_config("base64-ciphertext")
    assert result["role"] == "buyer"
    assert result["budget_cap"] == 5000000
```

---

## API Tests (pytest)

### What They Cover

| Test Area | Description |
|-----------|-------------|
| **Session Routes** | CRUD operations, input validation, error handling |
| **Onboard Routes** | Party onboarding, encrypted/plaintext config, role validation |
| **Negotiate Routes** | Start negotiation, status polling, timeout handling |
| **Attestation Routes** | Attestation retrieval, verification |
| **Audit Routes** | Session audit, admin audit, authorization |
| **Auth Middleware** | Firebase ID token verification, token extraction, public path bypass, MFA check |
| **Audit Middleware** | Audit entry creation, response headers |
| **Rate Limit Middleware** | Sliding window, threshold enforcement, health exemption |
| **Firestore Client** | CRUD operations, error handling |
| **WebSocket Manager** | Connection management, broadcast, disconnect cleanup |

### Setup

```bash
cd /path/to/accord/app

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install test dependencies
pip install pytest pytest-cov pytest-asyncio pytest-mock httpx
# httpx is needed for FastAPI TestClient (ASGI transport)
```

### Running Tests

```bash
# Run all API tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html

# Run specific test modules
pytest tests/test_sessions.py -v
pytest tests/test_auth.py -v
pytest tests/test_audit.py -v

# Run with async support
pytest tests/ -v --asyncio-mode=auto
```

### Mocking Strategy

The API tests mock external dependencies:

| Dependency | Mock Strategy |
|-----------|---------------|
| Firestore | Mock `google.cloud.firestore.Client` methods or use `firestore_emulator` |
| Firebase Auth | Mock `firebase_admin.auth.verify_id_token` to return test claims |
| Cloud KMS | Mock `google.cloud.kms.KeyManagementServiceClient` |
| GCE Metadata | Mock HTTP requests to `metadata.google.internal` |

**Example: Testing session creation with mocked Firestore:**

```python
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from server import app

@patch("routes.sessions.firestore_client")
@patch("auth.firebase_admin.auth.verify_id_token")
def test_create_session(mock_verify, mock_firestore):
    # Mock Firebase Auth
    mock_verify.return_value = {
        "uid": "test-uid",
        "email": "test@example.com",
        "firebase": {"sign_in_second_factor": "totp"},
    }

    # Mock Firestore
    mock_doc = MagicMock()
    mock_firestore.collection.return_value.document.return_value = mock_doc

    client = TestClient(app)
    response = client.post(
        "/api/v1/sessions",
        json={"max_duration_sec": 3600, "description": "Test session"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "awaiting_parties"
```

**Example: Testing MFA enforcement:**

```python
@patch("auth.firebase_admin.auth.verify_id_token")
def test_mfa_required(mock_verify):
    """Verify requests without MFA are rejected."""
    mock_verify.return_value = {
        "uid": "test-uid",
        "email": "test@example.com",
        "firebase": {},  # No sign_in_second_factor
    }

    client = TestClient(app)
    response = client.get(
        "/api/v1/sessions",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 401
    assert "MFA" in response.json()["detail"]
```

---

## Frontend Tests (Jest + React Testing Library)

### What They Cover

| Test Area | Description |
|-----------|-------------|
| **Components** | Render testing, user interaction, prop handling |
| **Auth Flow** | Sign-in form, MFA input, error states (Firebase Auth) |
| **Session Management** | Session list, creation form, status display |
| **Agent Configuration** | Config form, disclosure tier selection, validation |
| **Attestation** | Image digest display, verification UI, SEV-SNP status |
| **Negotiation Monitor** | Round progress, outcome display, WebSocket updates |
| **Audit Viewer** | Log table rendering, filtering |
| **API Integration** | API client functions, error handling, token refresh |
| **Hooks** | Custom React hooks for auth, sessions, WebSocket |

### Setup

```bash
cd /path/to/accord/frontend

# Install dependencies
npm install

# Install test dependencies (typically already in devDependencies)
npm install --save-dev jest @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

### Running Tests

```bash
# Run all tests
npm test

# Run with coverage
npm test -- --coverage

# Run in watch mode (re-runs on file changes)
npm test -- --watch

# Run a specific test file
npm test -- --testPathPattern="SessionList"

# Run tests matching a description
npm test -- -t "should create a session"

# Generate coverage report
npm test -- --coverage --coverageReporters=text --coverageReporters=html
```

### Test Configuration

Typical `jest.config.js` for Next.js:

```javascript
const nextJest = require('next/jest')

const createJestConfig = nextJest({
  dir: './',
})

const customJestConfig = {
  setupFilesAfterSetup: ['<rootDir>/jest.setup.js'],
  testEnvironment: 'jsdom',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/**/index.ts',
  ],
}

module.exports = createJestConfig(customJestConfig)
```

### Example Test

```typescript
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SessionCreationForm } from '@/components/SessionCreationForm';

describe('SessionCreationForm', () => {
  it('should submit session creation request', async () => {
    const onSubmit = jest.fn().mockResolvedValue({ session_id: 'test-id' });
    render(<SessionCreationForm onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByLabelText(/description/i),
      'Test negotiation'
    );
    await userEvent.selectOptions(
      screen.getByLabelText(/use case/i),
      'vc_funding'
    );
    await userEvent.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        description: 'Test negotiation',
        use_case: 'vc_funding',
        max_duration_sec: 3600,
      });
    });
  });

  it('should display validation errors', async () => {
    render(<SessionCreationForm onSubmit={jest.fn()} />);

    // Try to submit empty form if description is required
    await userEvent.click(screen.getByRole('button', { name: /create/i }));

    // Check for validation feedback
    expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument();
  });
});
```

---

## E2E Tests (Playwright)

### What They Cover

End-to-end tests exercise the complete user journey through the web interface, interacting with the real (or staged) backend.

| Test Scenario | Description |
|---------------|-------------|
| **Auth Flow** | Sign up, sign in, MFA setup (TOTP via Firebase Auth), token refresh, sign out |
| **Session Lifecycle** | Create session, configure agents, onboard, start, view result |
| **Attestation** | View attestation, verify image digest and SEV-SNP status |
| **Negotiation** | Full negotiation with deal outcome, no-deal outcome |
| **Audit** | View session audit log, admin audit view |
| **Error Handling** | Invalid session, network errors, expired tokens |

### Setup

```bash
cd /path/to/accord/frontend

# Install Playwright
npm install --save-dev @playwright/test

# Install browsers
npx playwright install

# Install system dependencies (Linux only)
npx playwright install-deps
```

### Configuration

`playwright.config.ts`:

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

### Running Tests

```bash
# Run all E2E tests
npx playwright test

# Run with UI (interactive mode)
npx playwright test --ui

# Run a specific test file
npx playwright test tests/e2e/negotiation.spec.ts

# Run in headed mode (visible browser)
npx playwright test --headed

# Run specific browser only
npx playwright test --project=chromium

# Generate test report
npx playwright show-report

# Run against a specific environment
E2E_BASE_URL=https://staging.accord.example.com npx playwright test
```

### Example Test

```typescript
import { test, expect } from '@playwright/test';

test.describe('Negotiation Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Sign in via Firebase Auth
    await page.goto('/auth/signin');
    await page.fill('[name="email"]', 'test@example.com');
    await page.fill('[name="password"]', 'TestP@ssw0rd123!');
    await page.click('button[type="submit"]');
    // Complete TOTP MFA...
    await page.waitForURL('/dashboard');
  });

  test('should create and complete a negotiation session', async ({ page }) => {
    // Create session
    await page.click('text=New Session');
    await page.fill('[name="description"]', 'E2E Test Session');
    await page.selectOption('[name="use_case"]', 'ma');
    await page.click('text=Create Session');

    // Verify session created
    await expect(page.locator('text=awaiting_parties')).toBeVisible();

    // Verify attestation
    await page.click('text=Verify Attestation');
    await expect(page.locator('text=Image Digest')).toBeVisible();
    await expect(page.locator('text=SEV-SNP')).toBeVisible();
  });
});
```

---

## Infrastructure Tests (Terraform)

### What They Cover

Terraform module validation checks for:

| Check | Tool | Description |
|-------|------|-------------|
| **Syntax and validity** | `terraform validate` | Valid HCL, correct resource types and property names |
| **Linting** | `tflint` | Best practices, deprecated features, naming conventions |
| **Security scanning** | `tfsec` | Security misconfigurations, compliance violations |
| **Plan verification** | `terraform plan` | Previews changes, detects drift |

### Setup

```bash
# Install tflint
brew install tflint  # macOS
# or: curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

# Install tfsec
brew install tfsec  # macOS
# or: curl -s https://raw.githubusercontent.com/aquasecurity/tfsec/master/scripts/install_linux.sh | bash

# Install Terraform (if not already)
brew install terraform  # macOS
```

### Running Tests

```bash
cd infrastructure/

# Validate Terraform configuration
terraform init -backend=false
terraform validate

# Lint with tflint
tflint --init
tflint --recursive

# Security scan with tfsec
tfsec .

# Detailed security scan with custom severity threshold
tfsec . --minimum-severity HIGH

# Plan (requires GCP credentials)
terraform plan -out=tfplan

# Output plan as JSON for automated analysis
terraform show -json tfplan > plan.json
```

### Example tflint Configuration

`.tflint.hcl`:

```hcl
config {
  module = true
}

plugin "google" {
  enabled = true
  version = "0.27.1"
  source  = "github.com/terraform-linters/tflint-ruleset-google"
}

rule "terraform_naming_convention" {
  enabled = true
}

rule "terraform_documented_outputs" {
  enabled = true
}

rule "terraform_documented_variables" {
  enabled = true
}
```

### Example tfsec Checks

tfsec will flag issues such as:
- Cloud KMS keys without rotation enabled
- Firewall rules that are too permissive
- Cloud Storage buckets without encryption or uniform access
- Service accounts with overly broad permissions
- Confidential VM not enabled on instance templates

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Accord CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  engine-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd app
          python -m venv .venv
          source .venv/bin/activate
          pip install pydantic==2.10.* cryptography==44.0.* scipy==1.14.*
          pip install google-cloud-firestore google-cloud-kms google-cloud-storage firebase-admin
          pip install pytest pytest-cov pytest-mock

      - name: Run engine tests
        run: |
          cd app
          source .venv/bin/activate
          pytest tests/ -v --cov=. --cov-report=xml --junitxml=junit-engine.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: app/coverage.xml
          flags: engine

  api-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd app
          python -m venv .venv
          source .venv/bin/activate
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio pytest-mock httpx

      - name: Run API tests
        run: |
          cd app
          source .venv/bin/activate
          pytest tests/ -v --cov=. --cov-report=xml --junitxml=junit-api.xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: app/coverage.xml
          flags: api

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Install dependencies
        run: |
          cd frontend
          npm ci

      - name: Run tests
        run: |
          cd frontend
          npm test -- --coverage --watchAll=false

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: frontend/coverage/lcov.info
          flags: frontend

  e2e-tests:
    runs-on: ubuntu-latest
    needs: [engine-tests, api-tests, frontend-tests]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'

      - name: Install dependencies
        run: |
          cd frontend
          npm ci
          npx playwright install --with-deps

      - name: Run E2E tests
        run: |
          cd frontend
          npx playwright test
        env:
          E2E_BASE_URL: ${{ secrets.STAGING_URL }}

      - name: Upload Playwright report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: frontend/playwright-report/

  infrastructure-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: '1.5'

      - name: Install tflint
        run: |
          curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash

      - name: Install tfsec
        run: |
          curl -s https://raw.githubusercontent.com/aquasecurity/tfsec/master/scripts/install_linux.sh | bash

      - name: Validate Terraform
        run: |
          cd infrastructure
          terraform init -backend=false
          terraform validate

      - name: Lint Terraform
        run: |
          cd infrastructure
          tflint --init
          tflint --recursive

      - name: Security scan
        run: |
          cd infrastructure
          tfsec . --minimum-severity HIGH

  docker-build:
    runs-on: ubuntu-latest
    needs: [engine-tests, api-tests]
    steps:
      - uses: actions/checkout@v4

      - name: Build container image
        run: docker build -t accord-app:ci .

      - name: Verify image builds successfully
        run: docker images accord-app:ci
```

### Test Execution Order in CI

```
1. [Parallel] Engine tests + API tests + Frontend tests + Infrastructure tests
2. [Parallel] Docker build (depends on engine + API tests)
3. [Sequential] E2E tests (depends on all unit test jobs passing)
4. [Sequential] Deploy to staging (if on main branch and all tests pass)
5. [Sequential] Smoke tests against staging
```

### Minimum Test Requirements for Merge

| Check | Required to Pass |
|-------|-----------------|
| Engine tests | All passing, >= 90% coverage |
| API tests | All passing, >= 85% coverage |
| Frontend tests | All passing, >= 80% coverage |
| Infrastructure validation | `terraform validate` passes |
| Infrastructure lint | `tflint` zero errors (warnings allowed) |
| Infrastructure security | `tfsec` zero HIGH/CRITICAL findings |
| Docker build | Image builds successfully |
| E2E tests | All critical paths passing |
