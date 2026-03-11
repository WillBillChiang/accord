# Firebase Setup Guide

## Document Control

| Field | Value |
|-------|-------|
| Classification | Internal |
| Compliance Scope | SOC 2 Type II (CC5, CC6), ISO 27001 (A.5.15, A.8.5, A.8.24) |
| Last Updated | 2026-03-11 |
| Related Documents | `architecture.md`, `security-model.md`, `compliance.md`, `deployment-guide.md` |

---

## 1. Overview

Accord uses two Firebase services for its frontend layer:

| Service | Purpose | Replaces |
|---------|---------|----------|
| **Firebase Auth** | User authentication with email/password and TOTP MFA (time-based one-time password multi-factor authentication) | AWS Cognito |
| **Firebase App Hosting** | Next.js 15 SSR deployment with automatic builds from source | AWS Amplify |

Both services operate within the same GCP project that hosts the Confidential VM backend infrastructure. Firebase Auth issues ID tokens that the backend (FastAPI on Confidential VM) verifies on every request using the `firebase-admin` SDK. TOTP MFA is enforced at both the frontend (enrollment/sign-in) and backend (token claim verification) layers.

### Architecture Context

```
Browser
  |
  |  Firebase Auth (ID tokens, TOTP MFA)
  |
  v
Firebase App Hosting (Next.js 15 SSR)
  |
  |  Bearer <ID token>
  |
  v
Cloud Load Balancer + Cloud Armor
  |
  v
Confidential VM (FastAPI)
  |-- firebase-admin.auth.verify_id_token(token, check_revoked=True)
  |-- Checks claims["firebase"]["sign_in_second_factor"] == "totp"
```

---

## 2. Firebase Project Setup

### 2.1. Create Firebase Project Linked to GCP

Firebase projects are GCP projects. Link Firebase to the existing Accord GCP project:

```bash
# Prerequisite: gcloud and firebase CLIs authenticated
PROJECT_ID=$(gcloud config get-value project)

# Enable required APIs
gcloud services enable \
  firebase.googleapis.com \
  identitytoolkit.googleapis.com \
  firebasehosting.googleapis.com \
  firebaseapphosting.googleapis.com \
  --project="$PROJECT_ID"

# Add Firebase to the existing GCP project
firebase projects:addfirebase "$PROJECT_ID"
```

### 2.2. Enable Firebase Auth with Email/Password Provider

1. Open the [Firebase Console](https://console.firebase.google.com/) and select the project.
2. Navigate to **Authentication > Sign-in method**.
3. Enable **Email/Password** provider.
4. Leave "Email link (passwordless sign-in)" **disabled** (password-based auth with MFA is required for SOC 2 compliance).

### 2.3. Enable TOTP MFA

1. In the Firebase Console, navigate to **Authentication > Sign-in method**.
2. Scroll to **Multi-factor authentication**.
3. Click **Enable**.
4. Under "Second factors," enable **TOTP (Time-based one-time password)**.
5. Set the MFA enforcement mode to **Required** for all users.

### 2.4. Configure Password Policy

In **Authentication > Settings > Password policy**:

| Setting | Value | Rationale |
|---------|-------|-----------|
| Minimum length | 12 characters | SOC 2 CC6.1 / ISO 27001 A.8.5 |
| Require uppercase | Yes | |
| Require lowercase | Yes | |
| Require number | Yes | |
| Require symbol | Yes | |

### 2.5. Enable Email Enumeration Protection

In **Authentication > Settings**:

- Enable **Email enumeration protection** to prevent attackers from discovering valid email addresses via sign-in/sign-up error messages.

### 2.6. Configure Authorized Domains

In **Authentication > Settings > Authorized domains**, add:

| Domain | Purpose |
|--------|---------|
| `localhost` | Local development (remove in production if not needed) |
| `<project-id>.firebaseapp.com` | Default Firebase domain |
| `<project-id>.web.app` | Default Firebase domain |
| `app.accord.example.com` | Production custom domain |

Remove any domains that should not be authorized. Unauthorized domains cannot host Firebase Auth sign-in flows.

---

## 3. Firebase Auth Configuration

### 3.1. Frontend Configuration

The Firebase client SDK is initialized in `frontend/src/lib/firebase.ts`:

```typescript
// frontend/src/lib/firebase.ts
'use client';

import { initializeApp, getApps } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY || '',
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN || '',
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || '',
};

const app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
export const auth = getAuth(app);
```

Required environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase Web API key (found in Firebase Console > Project settings) | `AIzaSy...` |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain | `accord-prod.firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase/GCP project ID | `accord-prod` |

The `NEXT_PUBLIC_` prefix makes these variables available in client-side code. The Firebase API key is safe to expose publicly; it only identifies the project and does not grant any server-side access. Authentication security is enforced by Firebase Security Rules and backend token verification.

### 3.2. Backend Enforcement

The backend middleware (`app/middleware/auth.py`) verifies Firebase ID tokens on every protected request:

```python
from firebase_admin import auth

# verify_id_token checks:
#   - RS256 signature against Google's public keys (auto-fetched and cached)
#   - Token expiry (ID tokens are valid for 1 hour)
#   - Audience (must match Firebase project ID)
#   - Issuer (must be https://securetoken.google.com/<project-id>)
# check_revoked=True also checks if the token has been revoked
decoded_token = auth.verify_id_token(token, check_revoked=True)
```

### 3.3. MFA Enforcement on the Backend

After verifying the token signature, the middleware checks that TOTP MFA was completed during sign-in:

```python
firebase_claims = decoded_token.get("firebase", {})
sign_in_second_factor = firebase_claims.get("sign_in_second_factor")

if sign_in_second_factor != "totp":
    raise ValueError("TOTP MFA is required for all protected endpoints")
```

This is a critical security control. Even if a user has a valid password, requests without completed TOTP verification are rejected by the backend. This prevents:
- Stolen password attacks (the attacker would also need the TOTP device).
- Frontend bypass attacks (an attacker calling the API directly without completing MFA).

### 3.4. Custom Claims for Admin Role

Admin users receive a custom claim `admin: true` set via the Firebase Admin SDK:

```python
import firebase_admin
from firebase_admin import auth as firebase_auth

# Set admin claim (run once per admin user)
firebase_auth.set_custom_user_claims(uid, {'admin': True})
```

The backend middleware reads this claim from the verified token:

```python
if claims.get("admin"):
    request.state.groups = list(set(request.state.groups + ["admin"]))
```

Custom claims propagate to the client on the next token refresh (within 1 hour, or forced via `getIdToken(true)`).

---

## 4. MFA Enrollment Flow

Users who sign up must enroll in TOTP MFA before they can access protected resources. The enrollment flow works as follows:

### 4.1. Flow Diagram

```
Sign Up
  |
  v
Account created (no MFA yet)
  |
  v
Redirect to /mfa-setup
  |
  v
Generate TOTP secret (TotpMultiFactorGenerator.generateSecret())
  |
  v
Display QR code (user scans with authenticator app)
  |
  v
User enters 6-digit verification code
  |
  v
multiFactor(user).enroll(assertion, "TOTP") -- MFA enrolled
  |
  v
Redirect to dashboard
```

### 4.2. Implementation

```typescript
import {
  multiFactor,
  TotpMultiFactorGenerator,
  TotpSecret,
  type User,
} from 'firebase/auth';

async function enrollTotp(user: User): Promise<TotpSecret> {
  // 1. Start a multi-factor enrollment session
  const multiFactorSession = await multiFactor(user).getSession();

  // 2. Generate a TOTP secret bound to this user and session
  const totpSecret = await TotpMultiFactorGenerator.generateSecret(
    multiFactorSession
  );

  // 3. Generate QR code URI for the authenticator app
  //    The user scans this QR code with Google Authenticator, Authy, etc.
  const qrCodeUri = totpSecret.generateQrCodeUrl(
    user.email || 'user',      // account name displayed in authenticator
    'Accord'                    // issuer name displayed in authenticator
  );

  // 4. Display qrCodeUri as a QR code image in the UI
  //    (use a library like 'qrcode' to render)

  return totpSecret;
}

async function verifyAndEnroll(
  user: User,
  totpSecret: TotpSecret,
  verificationCode: string
): Promise<void> {
  // 5. User enters the 6-digit code from their authenticator app
  const multiFactorAssertion =
    TotpMultiFactorGenerator.assertionForEnrollment(
      totpSecret,
      verificationCode
    );

  // 6. Enroll the TOTP factor
  await multiFactor(user).enroll(multiFactorAssertion, 'TOTP');
}
```

### 4.3. Security Requirements for MFA Enrollment

| Requirement | Implementation | Compliance Reference |
|-------------|---------------|---------------------|
| MFA must be enrolled before accessing protected resources | Frontend redirects unenrolled users to `/mfa-setup`; backend rejects tokens without `sign_in_second_factor == "totp"` | SOC 2 CC6.1, ISO 27001 A.8.5 |
| TOTP secret is generated server-side by Firebase | `TotpMultiFactorGenerator.generateSecret()` uses Firebase's server-side key generation | ISO 27001 A.8.24 |
| Verification code must be validated before enrollment completes | `assertionForEnrollment()` + `multiFactor(user).enroll()` verifies the code is correct before persisting | SOC 2 CC6.1 |

---

## 5. MFA Sign-in Flow

When a user with enrolled MFA signs in, Firebase Auth raises a `MultiFactorError` after the first factor (password) succeeds. The frontend must resolve this by collecting the TOTP code.

### 5.1. Flow Diagram

```
Sign In (email + password)
  |
  v
Firebase Auth validates password (first factor)
  |
  v
auth/multi-factor-auth-required error thrown
  |
  v
UI prompts for 6-digit TOTP code
  |
  v
TotpMultiFactorGenerator.assertionForSignIn()
  |
  v
resolver.resolveSignIn(assertion) -- sign-in complete
  |
  v
ID token issued with sign_in_second_factor: "totp"
```

### 5.2. Implementation

The sign-in flow is implemented in `frontend/src/lib/auth.ts`. Key excerpts:

```typescript
import {
  signInWithEmailAndPassword,
  getMultiFactorResolver,
  TotpMultiFactorGenerator,
  type MultiFactorError,
  type MultiFactorResolver,
} from 'firebase/auth';

// Step 1: Attempt sign-in (catches MFA requirement)
async function signIn(email: string, password: string): Promise<void> {
  try {
    await signInWithEmailAndPassword(auth, email, password);
  } catch (error: unknown) {
    const firebaseError = error as { code?: string };
    if (firebaseError.code === 'auth/multi-factor-auth-required') {
      // Step 2: Extract the MFA resolver
      const mfaError = error as MultiFactorError;
      const resolver = getMultiFactorResolver(auth, mfaError);

      // Store resolver in state -- UI will prompt for TOTP code
      setMfaResolver(resolver);
      setMfaRequired(true);
      return;
    }
    throw error;
  }
}

// Step 3: Resolve MFA with TOTP code (called after user enters code)
async function resolveMfa(
  resolver: MultiFactorResolver,
  verificationCode: string
): Promise<void> {
  // Find the TOTP hint in the resolver's hints
  const totpHint = resolver.hints.find(
    (hint) => hint.factorId === TotpMultiFactorGenerator.FACTOR_ID
  );

  if (!totpHint) {
    throw new Error('No TOTP factor enrolled');
  }

  // Create the assertion with the user's 6-digit code
  const assertion = TotpMultiFactorGenerator.assertionForSignIn(
    totpHint.uid,
    verificationCode
  );

  // Complete sign-in -- this returns a UserCredential with a valid ID token
  await resolver.resolveSignIn(assertion);
}
```

After `resolveSignIn()` completes, the user's ID token includes the claim `firebase.sign_in_second_factor: "totp"`, which the backend middleware requires for all protected endpoints.

---

## 6. Firebase App Hosting

Firebase App Hosting provides managed deployment for Next.js SSR applications. It builds from source, provisions Cloud Run backends, and manages SSL certificates and CDN automatically.

### 6.1. `firebase.json` Configuration

The `firebase.json` file in the frontend directory configures security headers:

```json
{
  "hosting": {
    "source": ".",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "headers": [
      {
        "source": "**/*",
        "headers": [
          {
            "key": "Strict-Transport-Security",
            "value": "max-age=63072000; includeSubDomains; preload"
          },
          {
            "key": "X-Content-Type-Options",
            "value": "nosniff"
          },
          {
            "key": "X-Frame-Options",
            "value": "DENY"
          },
          {
            "key": "X-XSS-Protection",
            "value": "1; mode=block"
          },
          {
            "key": "Referrer-Policy",
            "value": "strict-origin-when-cross-origin"
          },
          {
            "key": "Permissions-Policy",
            "value": "camera=(), microphone=(), geolocation=()"
          },
          {
            "key": "Content-Security-Policy",
            "value": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://*.googleapis.com https://*.firebaseapp.com wss://*; font-src 'self' data:; frame-ancestors 'none';"
          }
        ]
      }
    ]
  }
}
```

#### Security Headers Explained

| Header | Value | Purpose | Compliance |
|--------|-------|---------|------------|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Forces HTTPS for 2 years, submits to browser preload lists | SOC 2 CC6.7, ISO 27001 A.5.14 |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME-type sniffing | ISO 27001 A.8.26 |
| `X-Frame-Options` | `DENY` | Prevents clickjacking by disallowing framing | ISO 27001 A.8.26 |
| `X-XSS-Protection` | `1; mode=block` | Legacy XSS filter (defense in depth) | ISO 27001 A.8.26 |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limits referrer information leakage | ISO 27001 A.8.12 |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Disables unnecessary browser APIs | ISO 27001 A.8.26 |
| `Content-Security-Policy` | (see value above) | Restricts resource origins, prevents XSS | SOC 2 CC6.6, ISO 27001 A.8.26 |

### 6.2. `apphosting.yaml` Configuration

The `apphosting.yaml` file configures the App Hosting backend:

```yaml
runConfig:
  runtime: nodejs20
  concurrency: 80
  cpu: 1
  memoryMiB: 512
  minInstances: 0
  maxInstances: 10
env:
  - variable: NEXT_PUBLIC_API_URL
    value: ""
  - variable: NEXT_PUBLIC_WS_URL
    value: ""
  - variable: NEXT_PUBLIC_FIREBASE_API_KEY
    secret: FIREBASE_API_KEY
  - variable: NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
    value: ""
  - variable: NEXT_PUBLIC_FIREBASE_PROJECT_ID
    value: ""
```

Key configuration notes:

| Field | Value | Purpose |
|-------|-------|---------|
| `runtime` | `nodejs20` | Node.js 20 LTS for Next.js 15 SSR |
| `concurrency` | `80` | Max concurrent requests per instance |
| `minInstances` | `0` | Scale to zero in non-production (set to `1` in production for availability) |
| `maxInstances` | `10` | Upper bound on auto-scaling |
| `secret: FIREBASE_API_KEY` | References GCP Secret Manager | Avoids hardcoding the API key in the config file |

### 6.3. Deployment

```bash
cd frontend/

# Create a new App Hosting backend linked to a GitHub repository
firebase apphosting:backends:create \
  --project="$PROJECT_ID" \
  --location=us-central1

# The CLI will prompt for:
#   - GitHub repository URL
#   - Root directory (for monorepos): frontend/
#   - Branch: main
#   - Backend ID: accord-frontend
```

After initial setup, every push to the configured branch triggers an automatic build and deployment. Firebase App Hosting:

1. Clones the repository.
2. Runs `npm install` and `npm run build` (Next.js build).
3. Deploys the SSR application to Cloud Run.
4. Routes traffic through Firebase's CDN with the configured security headers.
5. Manages SSL certificates automatically.

#### Manual Deployment (if needed)

```bash
# Trigger a rollout manually
firebase apphosting:rollouts:create accord-frontend \
  --project="$PROJECT_ID" \
  --branch=main
```

---

## 7. Environment Variables

### 7.1. Complete Variable Reference

#### Frontend Variables (set in `apphosting.yaml` or `.env.local`)

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Yes | Firebase Console > Project settings | Firebase Web API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Yes | Firebase Console > Project settings | Firebase Auth domain (`<project-id>.firebaseapp.com`) |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Yes | Firebase Console > Project settings | Firebase/GCP project ID |
| `NEXT_PUBLIC_API_URL` | Yes | Deployment config | Backend API base URL (e.g., `https://api.accord.example.com`) |
| `NEXT_PUBLIC_WS_URL` | Yes | Deployment config | WebSocket base URL (e.g., `wss://api.accord.example.com`) |

#### Backend Variables (set in Confidential VM instance metadata or Secret Manager)

| Variable | Required | Source | Description |
|----------|----------|--------|-------------|
| `FIREBASE_PROJECT_ID` | Yes | Firebase Console | Firebase project ID for `verify_id_token` audience check |
| `GOOGLE_APPLICATION_CREDENTIALS` | Local dev only | GCP IAM | Path to service account key JSON (not used in production; production uses ADC) |
| `GCP_PROJECT_ID` | Yes | GCP Console | GCP project ID |
| `GCP_REGION` | Yes | Deployment config | GCP region (e.g., `us-central1`) |
| `KMS_KEY_NAME` | Yes | Terraform output | Cloud KMS key resource name |
| `FIRESTORE_DATABASE` | Yes | Terraform output | Firestore database name (typically `(default)`) |
| `CLOUD_STORAGE_AUDIT_BUCKET` | Yes | Terraform output | Audit log Cloud Storage bucket name |
| `CLOUD_STORAGE_DOCS_BUCKET` | Yes | Terraform output | Documents Cloud Storage bucket name |

### 7.2. `.env.local` Template for Development

Create `frontend/.env.local` for local development:

```bash
# frontend/.env.local
# DO NOT COMMIT THIS FILE -- it is listed in .gitignore

# Firebase Auth (get from Firebase Console > Project settings > Your apps)
NEXT_PUBLIC_FIREBASE_API_KEY=AIzaSy_your_dev_api_key_here
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-dev-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-dev-project

# Backend API (local development)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

**Security note**: Never commit `.env.local` or any file containing API keys to version control. The `.gitignore` file must include `.env.local` and `.env*.local`.

---

## 8. Security Considerations

### 8.1. Token Revocation Support

The backend verifies tokens with `check_revoked=True`, which checks the token against Firebase's revocation list on every request:

```python
decoded_token = auth.verify_id_token(token, check_revoked=True)
```

This enables immediate access revocation:

```python
# Revoke all refresh tokens for a user (e.g., after account compromise)
firebase_auth.revoke_refresh_tokens(uid)
```

After revocation, all existing ID tokens for that user are rejected. The user must re-authenticate.

**Performance note**: `check_revoked=True` adds a network call to Firebase on each request. This is acceptable for Accord's workload profile (low request volume per user). For high-throughput scenarios, consider caching the revocation check with a short TTL.

### 8.2. Session Management

| Aspect | Implementation |
|--------|---------------|
| ID token lifetime | 1 hour (Firebase default, not configurable) |
| Refresh token | Managed by Firebase SDK; automatically refreshes ID tokens before expiry |
| Session termination | Client calls `signOut()` which clears local auth state; backend continues to accept the ID token until it expires (max 1 hour) |
| Forced session termination | Call `firebase_auth.revoke_refresh_tokens(uid)` on the backend to invalidate all sessions |
| Concurrent sessions | Allowed by default; use token revocation to terminate all sessions if needed |

### 8.3. CORS Configuration

The backend (FastAPI) configures CORS to allow requests only from the frontend domain:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.accord.example.com",
        "https://<project-id>.web.app",
        "http://localhost:3000",  # Local development only -- remove in production
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
```

In production, remove `http://localhost:3000` from `allow_origins`. Restrict origins to the exact production domains.

### 8.4. Rate Limiting at Cloud Armor Level

Rate limiting is enforced at two layers:

| Layer | Mechanism | Threshold | Scope |
|-------|-----------|-----------|-------|
| Cloud Armor (WAF) | GCP-managed rate limiting rule on the Load Balancer | 2000 requests per 5 minutes per IP | All traffic to the backend |
| Application middleware | Sliding window rate limiter in FastAPI | 60 requests per minute per IP | All non-health-check endpoints |

Cloud Armor provides the first line of defense, blocking abusive IPs before traffic reaches the Confidential VM. The application-level rate limiter provides fine-grained control within the application.

Firebase Auth also has its own built-in rate limiting for authentication attempts (sign-in, sign-up, password reset), which protects against brute-force attacks on user credentials independent of the API rate limits.

### 8.5. Firebase Auth Security Checklist

| Control | Status | Verification |
|---------|--------|-------------|
| Email/password provider enabled | Required | Firebase Console > Authentication > Sign-in method |
| TOTP MFA enabled and required | Required | Firebase Console > Authentication > Sign-in method > Multi-factor auth |
| Email enumeration protection enabled | Required | Firebase Console > Authentication > Settings |
| Password policy (12+ chars, mixed case, numbers, symbols) | Required | Firebase Console > Authentication > Settings > Password policy |
| Authorized domains restricted to known domains | Required | Firebase Console > Authentication > Settings > Authorized domains |
| Backend enforces `check_revoked=True` | Required | `app/middleware/auth.py` |
| Backend enforces `sign_in_second_factor == "totp"` | Required | `app/middleware/auth.py` |
| Admin custom claims set via Admin SDK only | Required | Never set custom claims from client-side code |
| `.env.local` in `.gitignore` | Required | `frontend/.gitignore` |
| Firebase API key restricted in GCP Console | Required | APIs & Services > Credentials > API key > Restrictions |

---

## 9. Development Mode

### 9.1. Auth Bypass for Local Development

When `FIREBASE_PROJECT_ID` is not set, the backend auth middleware returns a development user without verifying the token. This allows local development without Firebase configuration:

```python
async def verify_token(token: str) -> dict:
    if not FIREBASE_PROJECT_ID:
        logger.warning("FIREBASE_PROJECT_ID not set -- skipping token verification")
        return {"uid": "dev-user", "email": "dev@localhost", "groups": ["admin"]}
    # ... production verification ...
```

**This behavior must never be active in production.** The `FIREBASE_PROJECT_ID` environment variable must always be set in the Confidential VM instance metadata or Secret Manager for production and staging environments. The deployment checklist in `deployment-guide.md` includes verification of this variable.

### 9.2. Firebase Auth Emulator for Local Testing

For local testing with real Firebase Auth behavior (MFA enrollment, token verification), use the Firebase Auth Emulator:

```bash
# Install Firebase CLI
npm install -g firebase-tools

# Start the Auth Emulator
firebase emulators:start --only auth --project=demo-accord
```

Configure the frontend to use the emulator by setting the environment variable before starting the development server:

```bash
# In a terminal, before running Next.js dev server
export FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099"
npm run dev
```

Alternatively, add emulator connection in the Firebase initialization code (for development only):

```typescript
import { connectAuthEmulator } from 'firebase/auth';

if (process.env.NODE_ENV === 'development') {
  connectAuthEmulator(auth, 'http://127.0.0.1:9099', {
    disableWarnings: true,
  });
}
```

The Auth Emulator provides:
- User creation and sign-in without real email verification.
- MFA enrollment and sign-in flows.
- Token generation that the backend can verify (when the backend is also configured to use the emulator).

For the backend to verify emulator tokens, set:

```bash
export FIREBASE_AUTH_EMULATOR_HOST="127.0.0.1:9099"
```

When this environment variable is set, `firebase-admin`'s `verify_id_token()` accepts tokens from the emulator without verifying them against Google's production public keys.

### 9.3. Full Local Development Setup

```bash
# Terminal 1: Start Firebase Auth Emulator
firebase emulators:start --only auth --project=demo-accord

# Terminal 2: Start the backend (without Firebase verification)
cd app/
export FIREBASE_PROJECT_ID=""  # Dev mode: skip verification
python -m uvicorn main:app --reload --port 8000

# Terminal 3: Start the frontend
cd frontend/
cp .env.local.example .env.local  # Edit with local values
npm run dev
```

---

## Appendix A: Retrieving Firebase Configuration Values

All frontend configuration values are available in the Firebase Console:

1. Open the [Firebase Console](https://console.firebase.google.com/).
2. Select your project.
3. Click the gear icon (Project settings).
4. Under **Your apps**, find the Web app (or create one if it does not exist).
5. The configuration object contains `apiKey`, `authDomain`, and `projectId`.

To retrieve values programmatically:

```bash
# Get the Web API key
gcloud services api-keys list --project="$PROJECT_ID" --format="value(name)"

# Get the project ID
gcloud config get-value project
```

## Appendix B: Creating the First Admin User

```bash
# From a machine with GOOGLE_APPLICATION_CREDENTIALS set,
# or from Cloud Shell:

python3 << 'PYEOF'
import firebase_admin
from firebase_admin import auth as firebase_auth

firebase_admin.initialize_app()

# Create the admin user
user = firebase_auth.create_user(
    email='admin@example.com',
    password='CHANGE_ME_Immediately_123!',
    email_verified=True,
)

# Set the admin custom claim
firebase_auth.set_custom_user_claims(user.uid, {'admin': True})

print(f'Created admin user: uid={user.uid}, email={user.email}')
print('IMPORTANT: Change the password immediately after first sign-in.')
print('IMPORTANT: Enroll TOTP MFA immediately after first sign-in.')
PYEOF
```

After running this script:

1. Sign in with the temporary password.
2. Change the password immediately.
3. Enroll TOTP MFA at `/mfa-setup`.
4. Verify that admin access works (e.g., view all audit logs).

## Appendix C: Revoking User Access

```python
import firebase_admin
from firebase_admin import auth as firebase_auth

firebase_admin.initialize_app()

# Option 1: Revoke all sessions (user must re-authenticate)
firebase_auth.revoke_refresh_tokens(uid)

# Option 2: Disable the account (user cannot sign in)
firebase_auth.update_user(uid, disabled=True)

# Option 3: Delete the account
firebase_auth.delete_user(uid)
```

All three options take effect immediately for new requests (with `check_revoked=True`). Existing ID tokens remain technically valid until expiry (up to 1 hour), but `check_revoked=True` catches revoked tokens on every request.
