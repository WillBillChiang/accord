# Accord API Reference

## Base URL

```
Production:  https://api.accord.example.com/api/v1
Development: http://localhost:8000/api/v1
```

## Authentication

All endpoints except `/health` and `GET /api/v1/attestation` require a valid Firebase Auth ID token in the `Authorization` header:

```
Authorization: Bearer <firebase_id_token>
```

Tokens are issued by Firebase Auth after email/password authentication + TOTP MFA verification. ID tokens are valid for 1 hour and are automatically refreshed by the Firebase client SDK.

### Obtaining a Token

Tokens are obtained via the Firebase Auth SDK (client-side) or REST API:

```javascript
// Firebase JS SDK (frontend)
import { getAuth } from 'firebase/auth';
const auth = getAuth();
const token = await auth.currentUser.getIdToken();
```

The backend verifies tokens using the Firebase Admin SDK, which automatically fetches and caches Google's public keys for RS256 signature verification.

### MFA Enforcement

The backend verifies that the `firebase.sign_in_second_factor` claim is present in the ID token, confirming TOTP MFA was completed. Requests with tokens lacking MFA verification are rejected with HTTP 401.

### Public Paths (No Auth Required)

- `GET /health`
- `GET /docs` (OpenAPI UI)
- `GET /openapi.json`
- `GET /api/v1/attestation`

---

## Sessions

### POST /api/v1/sessions

Create a new negotiation session.

**Request Body:**

```json
{
  "max_duration_sec": 3600,
  "description": "Series A funding negotiation",
  "use_case": "vc_funding"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `max_duration_sec` | integer | No | 3600 | Maximum session duration in seconds (60-86400) |
| `description` | string | No | `""` | Human-readable session description |
| `use_case` | string | No | `""` | Use case identifier: `"ma"`, `"ip_licensing"`, `"vc_funding"`, `"nda_replacement"` |

**Response (201):**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "awaiting_parties",
  "created_at": 1710100800.0,
  "created_by": "firebase-uid"
}
```

**Error Responses:**

| Code | Description |
|------|-------------|
| 401 | Missing or invalid authentication token, or MFA not completed |
| 422 | Validation error (e.g., `max_duration_sec` out of range) |
| 500 | Internal error |

---

### GET /api/v1/sessions

List all sessions for the authenticated user.

**Response (200):**

```json
{
  "sessions": [
    {
      "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "status": "awaiting_parties",
      "createdAt": 1710100800.0,
      "createdBy": "firebase-uid",
      "description": "Series A funding negotiation",
      "useCase": "vc_funding",
      "maxDurationSec": 3600,
      "sellerOnboarded": false,
      "buyerOnboarded": false
    }
  ]
}
```

**Error Responses:**

| Code | Description |
|------|-------------|
| 401 | Missing or invalid authentication token |

---

### GET /api/v1/sessions/{session_id}

Get session details including real-time status.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Response (200):**

```json
{
  "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "negotiating",
  "createdAt": 1710100800.0,
  "createdBy": "firebase-uid",
  "description": "Series A funding negotiation",
  "useCase": "vc_funding",
  "maxDurationSec": 3600,
  "sellerOnboarded": true,
  "buyerOnboarded": true,
  "sessionStatus": {
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "negotiating",
    "current_round": 3,
    "is_expired": false,
    "seller_onboarded": true,
    "buyer_onboarded": true,
    "log": [
      {
        "round": 1,
        "timestamp": 1710100810.0,
        "action": "proposal",
        "from_party": "seller-uuid",
        "price_offered": true,
        "terms_included": true
      }
    ]
  }
}
```

Note: The `sessionStatus.log` field contains a redacted negotiation log. Actual prices and terms are stripped -- only boolean indicators are returned.

**Error Responses:**

| Code | Description |
|------|-------------|
| 401 | Missing or invalid authentication token |
| 404 | Session not found |

---

### DELETE /api/v1/sessions/{session_id}

Terminate a session and trigger provable deletion.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Response (200):**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "outcome": "user_terminated",
  "reason": "user_terminated",
  "final_terms": null,
  "final_price": null,
  "rounds_completed": 0,
  "started_at": 1710100800.0,
  "completed_at": 1710101400.0
}
```

Upon termination, the application:
1. Destroys all ephemeral session encryption keys (cryptographic zeroing)
2. Zeros all party configurations and confidential data in memory
3. Clears the negotiation log
4. Returns the outcome to the caller

**Error Responses:**

| Code | Description |
|------|-------------|
| 401 | Missing or invalid authentication token |
| 404 | Session not found |

---

## Onboarding

### POST /api/v1/sessions/{session_id}/onboard

Submit encrypted party configuration to the Confidential VM. In production, configuration and confidential data are Cloud KMS-encrypted client-side. Only the Confidential VM's service account can decrypt via Cloud KMS IAM.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Request Body (Production -- Cloud KMS-encrypted):**

```json
{
  "party_id": "optional-custom-party-id",
  "role": "seller",
  "encrypted_config": "base64-encoded-kms-ciphertext...",
  "encrypted_data": "base64-encoded-kms-ciphertext..."
}
```

**Request Body (Development -- plaintext):**

```json
{
  "role": "buyer",
  "config": {
    "role": "buyer",
    "budget_cap": 5000000.00,
    "reservation_price": 4500000.00,
    "max_rounds": 10,
    "max_concession_per_round": 0.15,
    "disclosure_fields": {
      "company_revenue": "must_disclose",
      "strategic_intent": "may_disclose",
      "board_approval_limit": "never_disclose"
    },
    "strategy_notes": "Prefer milestone-based payment structure. Emphasize synergies.",
    "priority_issues": ["price", "payment_terms", "transition_timeline"],
    "acceptable_deal_structures": ["asset_purchase", "stock_purchase"],
    "confidential_data": {
      "board_approval_limit": 5500000,
      "competing_offers": 2,
      "internal_valuation": 4200000
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `party_id` | string | No | Custom party identifier (auto-generated UUID if omitted) |
| `role` | string | Yes | Must be `"seller"` or `"buyer"` |
| `encrypted_config` | string | No* | Base64-encoded Cloud KMS-encrypted party configuration |
| `encrypted_data` | string | No* | Base64-encoded Cloud KMS-encrypted confidential data |
| `config` | object | No* | Plaintext party configuration (development mode only) |

*Either `encrypted_config` or `config` should be provided.

**Party Config Schema:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `role` | string | Yes | - | `"seller"` or `"buyer"` |
| `budget_cap` | float | Yes | - | Maximum price (buyer) or minimum acceptable price (seller). Must be > 0. |
| `reservation_price` | float | Yes | - | Walk-away price. Must be > 0. |
| `max_rounds` | integer | No | 10 | Maximum negotiation rounds (1-50) |
| `max_concession_per_round` | float | No | 0.15 | Maximum concession rate per round (0.01-1.0) |
| `disclosure_fields` | object | No | `{}` | Map of field names to disclosure tiers: `"must_disclose"`, `"may_disclose"`, `"never_disclose"` |
| `strategy_notes` | string | No | `""` | Free-text strategy guidance for the AI agent |
| `priority_issues` | array | No | `[]` | Ordered list of priority negotiation issues |
| `acceptable_deal_structures` | array | No | `[]` | List of acceptable deal structures |
| `confidential_data` | object | No | `{}` | Confidential data fields (only accessible inside Confidential VM) |

**Response (200):**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "onboarding",
  "party_id": "generated-party-uuid",
  "role": "seller"
}
```

When both parties are onboarded, the status transitions to `"zopa_check"`.

**Error Responses:**

| Code | Description |
|------|-------------|
| 400 | Onboarding error (e.g., party already onboarded, invalid config) |
| 401 | Missing or invalid authentication token |
| 404 | Session not found |
| 422 | Validation error |

---

## Negotiation

### POST /api/v1/sessions/{session_id}/start

Start the negotiation for a session. Both parties must be onboarded. The application executes the full negotiation protocol and returns the outcome.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Request Body:** None

**Response (200) -- Deal Reached:**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "outcome": "deal_reached",
  "reason": "deal_reached",
  "final_terms": {
    "payment_structure": "milestone-based",
    "transition_period": "6 months"
  },
  "final_price": 4750000.00,
  "rounds_completed": 5,
  "started_at": 1710100800.0,
  "completed_at": 1710101100.0
}
```

**Response (200) -- No Deal:**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "outcome": "no_zopa",
  "reason": "no_zopa",
  "final_terms": null,
  "final_price": null,
  "rounds_completed": 0,
  "started_at": 1710100800.0,
  "completed_at": 1710100802.0
}
```

**Possible Outcome Values:**

| Outcome | Description |
|---------|-------------|
| `deal_reached` | Agreement reached through SAO or Nash Bargaining |
| `no_zopa` | No Zone of Possible Agreement (seller minimum > buyer maximum) |
| `no_agreement` | SAO exhausted and Nash Bargaining failed |
| `rejected` | One party's agent explicitly rejected |
| `timeout` | Session exceeded max duration |
| `agent_failure` | Agent generation failure |

**Error Responses:**

| Code | Description |
|------|-------------|
| 400 | Both parties not onboarded |
| 401 | Missing or invalid authentication token |
| 404 | Session not found |
| 500 | Internal error (session status set to `"error"`) |

**Timeout:** This endpoint has a 5-minute timeout for the full negotiation. For long-running negotiations, use the WebSocket endpoint for real-time progress.

---

### GET /api/v1/sessions/{session_id}/status

Get real-time negotiation status.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Response (200) -- Live Status:**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "negotiating",
  "current_round": 4,
  "is_expired": false,
  "seller_onboarded": true,
  "buyer_onboarded": true,
  "log": [
    {
      "round": 1,
      "timestamp": 1710100810.0,
      "action": "proposal",
      "from_party": "seller-uuid",
      "price_offered": true,
      "terms_included": true
    },
    {
      "round": 1,
      "timestamp": 1710100812.0,
      "action": "counter",
      "from_party": "buyer-uuid",
      "price_offered": null,
      "terms_included": null
    }
  ]
}
```

**Response (200) -- Fallback:**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "negotiating",
  "note": "Showing cached status from Firestore"
}
```

**Error Responses:**

| Code | Description |
|------|-------------|
| 404 | Session not found |

---

## Attestation

### GET /api/v1/attestation

Get the Confidential VM attestation information. Returns the container image digest, SEV-SNP status, and VM identity that cryptographically prove the code and security configuration running inside the Confidential VM. **This endpoint does not require authentication** to allow any party to verify before submitting data.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nonce` | string | No | Client-provided nonce for replay protection |

**Response (200):**

```json
{
  "image_digest": "sha256:a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd",
  "sev_snp_enabled": true,
  "secure_boot": true,
  "integrity_monitoring": true,
  "vm_id": "1234567890123456789",
  "timestamp": 1710100800.0,
  "nonce": "client-provided-nonce"
}
```

| Field | Description |
|-------|-------------|
| `image_digest` | SHA-256 digest of the container image running in the Confidential VM |
| `sev_snp_enabled` | Whether AMD SEV-SNP is active on this VM |
| `secure_boot` | Whether Shielded VM Secure Boot is enabled |
| `integrity_monitoring` | Whether Shielded VM integrity monitoring is enabled |
| `vm_id` | GCE instance unique identifier |
| `timestamp` | Unix timestamp of attestation generation |
| `nonce` | Echo of client-provided nonce (if any) |

**Error Responses:**

| Code | Description |
|------|-------------|
| 503 | Attestation information unavailable |

---

### POST /api/v1/attestation/verify

Verify Confidential VM attestation against expected values. Compares the live attestation information against caller-provided expected values.

**Request Body:**

```json
{
  "expected_image_digest": "sha256:a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd",
  "expected_sev_snp_enabled": true
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `expected_image_digest` | string | Yes | Expected container image digest |
| `expected_sev_snp_enabled` | boolean | No | Expected SEV-SNP status (defaults to `true`) |

**Response (200):**

```json
{
  "verified": true,
  "image_digest_match": true,
  "sev_snp_match": true,
  "attestation": {
    "image_digest": "sha256:a1b2c3d4e5f6...",
    "sev_snp_enabled": true,
    "secure_boot": true,
    "integrity_monitoring": true,
    "vm_id": "1234567890123456789",
    "timestamp": 1710100800.0,
    "nonce": null
  }
}
```

**Error Responses:**

| Code | Description |
|------|-------------|
| 422 | Validation error |
| 503 | Attestation information unavailable |

---

## Audit

### GET /api/v1/sessions/{session_id}/audit

Get audit log entries for a specific session. Returns redacted entries safe for external viewing.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Maximum entries to return (1-500) |

**Response (200):**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "audit_logs": [
    {
      "auditId": "log-uuid-1",
      "sessionId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "timestamp": 1710101100.0,
      "action": "negotiation_completed",
      "userId": "firebase-uid",
      "outcome": "deal_reached",
      "roundsCompleted": 5
    }
  ]
}
```

**Error Responses:**

| Code | Description |
|------|-------------|
| 401 | Missing or invalid authentication token |
| 422 | Validation error (limit out of range) |

---

### GET /api/v1/audit

Get audit logs. Admins (users with the `admin: true` custom claim in Firebase Auth) see all logs; non-admins see only their own.

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Maximum entries to return (1-500) |
| `user_id` | string | No | null | Filter by user ID (admin only) |

**Response (200):**

```json
{
  "audit_logs": [
    {
      "audit_id": "uuid",
      "timestamp": 1710101100.0,
      "request_id": "req-uuid",
      "user_id": "firebase-uid",
      "method": "POST",
      "path": "/api/v1/sessions/abc/start",
      "query_params": "",
      "status_code": 200,
      "duration_ms": 4523.45,
      "ip_address": "10.0.1.50",
      "user_agent": "Mozilla/5.0..."
    }
  ]
}
```

**Error Responses:**

| Code | Description |
|------|-------------|
| 401 | Missing or invalid authentication token |

---

## Health

### GET /health

Health check endpoint for Cloud Load Balancer health monitoring. No authentication required.

**Response (200):**

```json
{
  "status": "healthy",
  "service": "accord"
}
```

---

## WebSocket

### WS /ws/negotiations/{session_id}

WebSocket endpoint for real-time negotiation status updates. Provides push notifications as the negotiation progresses.

**Connection URL:**

```
wss://api.accord.example.com/ws/negotiations/{session_id}
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | Session identifier |

**Server-Sent Messages:**

Messages are JSON-encoded and pushed as the negotiation progresses:

```json
{
  "type": "round_update",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "round": 3,
  "action": "proposal",
  "from_role": "seller",
  "timestamp": 1710100830.0
}
```

```json
{
  "type": "negotiation_complete",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "outcome": "deal_reached",
  "rounds_completed": 5
}
```

**Client Commands:**

Clients can send text messages for basic control:

| Command | Description |
|---------|-------------|
| `subscribe` | Subscribe to updates for this session |
| `unsubscribe` | Unsubscribe from updates |

**Connection Lifecycle:**

1. Client connects to `wss://.../ws/negotiations/{session_id}`
2. Server accepts connection and adds to session's broadcast group
3. Server pushes status updates as negotiation progresses
4. Connection is cleaned up on disconnect or session termination

---

## Common Response Headers

All responses include the following headers:

| Header | Description |
|--------|-------------|
| `X-Request-ID` | Unique request identifier (from client header or auto-generated UUID) |
| `X-Audit-ID` | Audit log entry ID for this request |

## Rate Limiting

### Application-Level

All endpoints (except `/health`) are rate-limited to 60 requests per minute per IP address using a sliding window algorithm.

### Cloud Armor (WAF-Level)

Cloud Armor enforces a limit of 2000 requests per 5 minutes per IP. Additional Cloud Armor rules provide protection against OWASP Top 10 attacks and known-malicious IP addresses.

When rate limited, the API returns:

```json
{
  "detail": "Rate limit exceeded. Please retry later."
}
```

**HTTP Status:** 429 Too Many Requests

## Session Status Lifecycle

```
awaiting_parties --> onboarding --> zopa_check --> negotiating --> deal_reached
                                       |              |              |
                                       |              +--> no_deal   |
                                       |              |              |
                                       |              +--> expired   |
                                       |              |              |
                                       |              +--> error     |
                                       |                             |
                                       +--> (no ZOPA) --> no_deal   |
                                                                     |
                                              terminated <-----------+
```
