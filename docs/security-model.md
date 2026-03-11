# Accord Security Model

## Overview

Accord's security model is designed to protect the confidential negotiation data of two parties who do not trust each other and do not fully trust the platform operator. The system achieves this through a combination of hardware memory encryption (GCP Confidential VMs with AMD SEV-SNP), cryptographic enforcement (Cloud KMS IAM-bound keys), provable data deletion (Conditional Recall), and defense-in-depth across all layers.

This document describes the threat model, security mechanisms, and their implementation.

## Threat Model

### What We Protect Against

| Threat | Category | Mitigation |
|--------|----------|------------|
| Platform operator reads confidential data | Insider threat | Confidential VM (AMD SEV-SNP) encrypts all VM memory; cloud provider cannot read VM contents |
| Party A learns Party B's private constraints | Data exfiltration | All processing in Confidential VM; ZOPA returns boolean only; preflight blocks NEVER_DISCLOSE fields |
| Compromised VM host (hypervisor-level attack) | Infrastructure compromise | AMD SEV-SNP provides hardware-level isolation; VM memory is encrypted with per-VM key managed by the CPU |
| Modified application code | Supply chain / tampering | Image digest attestation; Shielded VM Secure Boot; parties verify before submitting data |
| Data persists after negotiation | Retention risk | Provable deletion: cryptographic zeroing + SEV-SNP key destroyed on VM termination |
| Network-based data exfiltration from VM | Network attack | VPC firewall restricts egress to Google APIs only; Private Google Access; no public internet routing |
| Man-in-the-middle on API | Network attack | TLS 1.2+, Cloud Armor, Private Google Access for Google services |
| Credential theft | Account compromise | Firebase Auth MFA (TOTP required), short-lived ID tokens (1 hour) |
| DDoS / abuse | Availability | Cloud Armor rate limiting, application-level rate limiting |
| Unauthorized API access | Access control | Firebase Auth ID token authentication on all protected endpoints |
| Audit log tampering | Compliance evasion | Cloud Storage Object Versioning, Cloud KMS encryption, Firestore for real-time logs, Cloud Audit Logs (automatic, tamper-evident) |

### Trust Assumptions

1. **AMD SEV-SNP hardware is trustworthy.** We trust that AMD's implementation of SEV-SNP provides the memory encryption guarantees documented in their specification. All VM memory is encrypted with a per-VM key managed by the AMD Secure Processor. The cloud provider (Google) cannot decrypt VM memory.

2. **Google Cloud KMS is trustworthy.** We trust that Cloud KMS enforces IAM conditions on key usage and does not allow decryption by unauthorized principals.

3. **The published code is auditable.** Parties can audit the open-source application code, build the container image themselves, and verify that the resulting image digest matches the deployed instance.

4. **Each party trusts their own client device.** Client-side encryption occurs on the user's browser/device. A compromised client device is outside the system's threat model.

## Confidential VM Isolation Properties

GCP Confidential VMs with AMD SEV-SNP provide the following hardware-enforced guarantees:

| Property | Description |
|----------|-------------|
| **Hardware memory encryption** | All VM memory is encrypted by the AMD Secure Processor using a per-VM encryption key. Even a compromised hypervisor or physical memory access cannot read VM contents. |
| **Secure Boot** | Shielded VM Secure Boot ensures the VM boots only with verified firmware and bootloaders, preventing boot-level tampering. |
| **vTPM-based integrity** | A virtual Trusted Platform Module provides measured boot, recording the boot chain for integrity verification. |
| **Launch measurement** | AMD SEV-SNP measures the initial VM launch state, providing a cryptographic attestation of the VM's initial configuration. |
| **Memory integrity protection** | SEV-SNP prevents hypervisor replay attacks, remapping attacks, and other memory manipulation attempts. |

### What This Means for Accord

- The cloud provider (Google) cannot read the parties' confidential data in VM memory, even with full infrastructure access.
- Confidential data exists in hardware-encrypted VM memory and is destroyed when the VM terminates (SEV-SNP key is discarded).
- The application processes data normally (no vsock relay needed) -- all protection is at the hardware level.

### Important Difference from Nitro Enclaves

Unlike the previous Nitro Enclave architecture, Confidential VMs **do have network access and disk access**. This is a fundamental architectural difference:

| Property | Nitro Enclaves (previous) | Confidential VMs (current) |
|----------|---------------------------|---------------------------|
| Network access | None (only vsock to parent) | Full network (restricted by firewall) |
| Disk access | None (RAM only, read-only rootfs) | Full disk (encrypted by default) |
| Shell access | None (no SSH, no debug) | SSH possible (restricted by IAM/firewall) |
| Memory encryption | Nitro Hypervisor isolation | AMD SEV-SNP hardware encryption |
| Attestation | PCR values from NSM (/dev/nsm) | OIDC tokens from GCE metadata with SEV-SNP claims |

### Compensating Controls

To address the network access difference, we implement the following compensating controls:

1. **VPC firewall rules restrict egress to Google APIs only.** The Confidential VM cannot reach the public internet. All outbound traffic is limited to Google service endpoints via Private Google Access (`restricted.googleapis.com`).

2. **No public IP address.** The VM is in a private subnet with no external IP.

3. **IAM and OS Login restrict SSH access.** SSH is disabled in production. Emergency access requires IAM authorization and is logged in Cloud Audit Logs.

4. **Confidential data is never written to disk.** Session data, party configurations, and encryption keys exist only in RAM. The application does not persist confidential data to the boot disk.

5. **Boot disk encryption.** The boot disk is encrypted with a Cloud KMS key, providing an additional layer of protection for application code at rest.

## Cloud KMS IAM-Bound Key Access

### Mechanism

The Accord Cloud KMS key restricts `cloudkms.cryptoKeyVersions.useToDecrypt` permission to the Confidential VM's service account via IAM:

```hcl
resource "google_kms_crypto_key_iam_member" "encrypter_decrypter" {
  crypto_key_id = google_kms_crypto_key.accord_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.confidential_vm.email}"
}
```

### Attestation via GCE Metadata

The Confidential VM can request an OIDC identity token from the GCE metadata service that includes SEV-SNP attestation claims:

```
GET http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=<audience>&format=full&licenses=TRUE
```

The returned OIDC token includes claims that attest:
- The VM is a Confidential VM with SEV-SNP enabled
- Secure Boot status
- Integrity monitoring status
- The VM's instance identity

### How It Works

1. Party encrypts their configuration client-side using `cloudkms.encrypt` with the Accord Cloud KMS key. No special IAM is required for encryption (any authenticated user can encrypt).
2. Encrypted blob is sent to the API, which runs inside the Confidential VM.
3. The application calls `cloudkms.decrypt` using the VM's service account credentials (obtained automatically from the GCE metadata service).
4. Cloud KMS verifies that the caller is the authorized service account and returns the decrypted plaintext.
5. The decrypted data exists only in the Confidential VM's hardware-encrypted memory.

This creates an IAM binding between the specific Confidential VM service account and the ability to decrypt party data. A compromised external server or a different VM cannot decrypt the data because it does not have the authorized service account credentials.

## Provable Deletion (Conditional Recall)

Accord implements the "credible forgetting" mechanism from Conditional Recall (arXiv:2510.21904). The core idea is that when a negotiation session ends, the system must provably destroy all confidential data so that it cannot be recovered by anyone, including the platform operator.

### Deletion Mechanism

When a session terminates (for any reason), the following sequence executes:

1. **Session key destruction**: The ephemeral AES-256-GCM session key is cryptographically zeroed using `ctypes.memset` to overwrite the key bytes with zeros. The `AESGCM` cipher object is nullified. Once destroyed, any data encrypted with this key is irrecoverable.

2. **Party configuration zeroing**: Both seller and buyer `PartyConfig` objects are recursively zeroed:
   - `confidential_data` dicts are recursively zeroed (all values overwritten)
   - String values are replaced with empty strings
   - Byte arrays are overwritten with zeros via `ctypes.memset`
   - Lists are cleared after recursive zeroing
   - Config references are set to `None`

3. **Negotiation log zeroing**: The entire negotiation log (which contains prices, terms, and rationale from each round) is recursively zeroed and cleared.

4. **Session object deletion**: The session is removed from the active sessions dictionary.

5. **VM termination (final assurance)**: When the Confidential VM terminates (or during MIG rolling updates), AMD SEV-SNP discards the per-VM memory encryption key. All VM memory becomes cryptographically irrecoverable at the hardware level.

### Code Path

```python
def _destroy_session_data(self) -> None:
    # 1. Destroy encryption keys
    self.key_manager.destroy()       # AES key zeroed with ctypes.memset

    # 2. Zero party configs
    if self.seller_config:
        secure_zero_dict(self.seller_config.confidential_data)
        self.seller_config = None

    if self.buyer_config:
        secure_zero_dict(self.buyer_config.confidential_data)
        self.buyer_config = None

    # 3. Zero negotiation log
    secure_zero_list(self.negotiation_log)
```

### Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Key material is irrecoverable | `ctypes.memset` zeros the raw bytes in memory |
| Encrypted data cannot be decrypted | Session key destroyed; no copy exists outside Confidential VM |
| Party configs are zeroed | Recursive zeroing of all dict/list/string/bytes values |
| Negotiation log is zeroed | Recursive zeroing before list clear |
| No persistent copy on disk | Application never writes confidential data to disk; RAM-only |
| Memory is physically irrecoverable on VM termination | AMD SEV-SNP key destroyed; encrypted memory pages cannot be decrypted |

## Side-Channel Mitigations

### AMD SEV-SNP Memory Encryption

All VM memory is encrypted at the hardware level by AMD SEV-SNP. This provides inherent protection against physical side-channel attacks (cold boot, bus probing) and hypervisor-level memory inspection.

### Timing Considerations

The LLM inference time introduces natural timing variance that masks the computational complexity of individual rounds. Future versions may add explicit timing normalization (fixed-delay responses) for stronger guarantees.

### Network Traffic Analysis

Since the Confidential VM architecture uses standard HTTPS (unlike the previous vsock architecture with fixed 64KB padding), network traffic analysis is a consideration. Mitigations include:

- TLS encryption on all traffic
- Cloud Armor provides additional traffic obfuscation through its proxy behavior
- Application responses do not leak confidential content (only redacted data leaves the application)

## Scope Condition: Phi(k, p, C)

From the NDAI framework, the scope condition defines when confidential data is accessible:

```
Phi(k, p, C) = True  iff:
    k = valid session key (not destroyed)
    p = attested Confidential VM (image digest matches, SEV-SNP active)
    C = active session context (not terminated)
```

When any component of the tuple becomes invalid:
- **k invalidated**: Session key is cryptographically zeroed -> data irrecoverable
- **p invalidated**: VM terminates or code changes -> SEV-SNP key destroyed, image digest changes, Cloud KMS IAM denies decryption from different service account
- **C invalidated**: Session terminates -> all in-memory data zeroed

The conjunction of all three conditions creates a narrow temporal window during which confidential data exists and is accessible, bounded exactly by the session lifetime.

## Client-Side Encryption Workflow

### Encryption Flow

```
1. Party fetches Accord Cloud KMS key name from the API
2. Party calls GET /api/v1/attestation to get image digest and SEV-SNP status
3. Party verifies image digest against published hash and confirms SEV-SNP is active
4. If verified, party encrypts their config:
   - config_json = JSON.stringify(party_config)
   - encrypted = CloudKMS.encrypt(name=accord_key, plaintext=config_json)
   - encrypted_b64 = base64_encode(encrypted.ciphertext)
5. Party sends encrypted_b64 to POST /sessions/{id}/onboard
```

### Security Properties

- The application receives the encrypted blob. Decryption requires the Confidential VM's service account credentials.
- Cloud KMS IAM allows `cloudkms.encrypt` for authenticated users, but `cloudkms.decrypt` requires the Confidential VM service account.
- Even if the load balancer or network is compromised, the attacker gets only encrypted blobs they cannot decrypt.

## Multi-Provider Threshold Architecture (Future)

The current architecture relies on a single cloud provider (GCP) for the TEE. Future versions will implement a multi-provider threshold architecture:

| Component | Current | Future |
|-----------|---------|--------|
| TEE Provider | GCP Confidential VMs only | GCP Confidential VMs + AWS Nitro Enclaves + Azure Confidential Computing |
| Key Management | Single Cloud KMS key | Threshold secret sharing across providers (e.g., 2-of-3) |
| Attestation | Single image digest + SEV-SNP | Cross-provider attestation verification |
| Trust Model | Trust GCP | Trust majority (e.g., 2 of 3 providers not colluding) |

This would eliminate the single-provider trust assumption and provide stronger guarantees against a compromised cloud provider.

## Authentication and Authorization

### Firebase Auth Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| MFA | Required (TOTP) | Prevents credential theft attacks |
| Password Policy | Min 12 chars, upper + lower + numbers + symbols | SOC 2 / ISO 27001 requirement |
| Email Enumeration Protection | Enabled | Prevents email discovery attacks |
| Token Validity | ID token: 1 hour, Refresh token: managed by Firebase | Limits session hijacking window |
| Auth Method | Email/password + TOTP MFA | Standard authentication with strong second factor |

### Firebase Auth ID Token Verification

The application validates Firebase ID tokens on every request:

1. Extract `Authorization: Bearer <token>` header.
2. Verify the ID token using the Firebase Admin SDK (`firebase_admin.auth.verify_id_token`).
3. The SDK automatically fetches and caches Google's public keys, verifies the signature (RS256), audience (Firebase project ID), and issuer (`https://securetoken.google.com/<project-id>`).
4. Extract claims: `uid` (user ID), `email`, custom claims (e.g., `admin: true`).
5. Verify that TOTP MFA was completed by checking the token's `firebase.sign_in_second_factor` claim.
6. Attach user identity to request state for downstream route handlers.

### Authorization

| Role | Firebase Custom Claim | Permissions |
|------|----------------------|-------------|
| User | (default) | CRUD own sessions, view own audit logs |
| Admin | `admin: true` | View all audit logs, manage all sessions |

## Network Security

### VPC Architecture

| Component | Security Control |
|-----------|-----------------|
| Confidential VM | Private subnet only (no public IP) |
| Cloud Load Balancer | Public-facing, HTTPS termination |
| Cloud NAT | Outbound internet for container image pulls (initialization only) |
| VPC Flow Logs | All traffic logged to Cloud Logging (365-day retention) |
| Private Google Access | Firestore, Cloud Storage, Cloud KMS, Cloud Logging traffic stays within Google network |

### Firewall Rules

The VPC firewall rules enforce:
- **Inbound**: HTTPS (443) from Cloud Load Balancer health check ranges and backend service only
- **Outbound**: HTTPS (443) to `restricted.googleapis.com` (199.36.153.4/30) only
- **Deny**: All other egress traffic (prevents the VM from reaching the public internet)
- No direct internet inbound access to the VM

### Cloud Armor (Web Application Firewall)

The Cloud Armor security policy attached to the Load Balancer backend includes:

| Rule | Description |
|------|-------------|
| Rate Limiting | 2000 requests per 5 minutes per IP |
| OWASP Top 10 | Protection against XSS, SQLi, RCE, LFI, RFI |
| Preconfigured WAF Rules | Google-managed rule sets for common web exploits |
| IP Reputation | Blocks requests from known-malicious IP addresses |
| Geo-blocking | Configurable country-level blocking |

### Application-Level Rate Limiting

In addition to Cloud Armor, the application implements a sliding window rate limiter:
- 60 requests per minute per IP address
- Exempt: `/health` endpoint (load balancer health checks)
- Returns HTTP 429 when exceeded

## Audit Trail Architecture

### Per-Request Audit Log

Every API request generates an audit entry containing:

| Field | Description |
|-------|-------------|
| `audit_id` | Unique audit entry UUID |
| `timestamp` | Unix timestamp |
| `request_id` | Request correlation ID |
| `user_id` | Authenticated user's Firebase UID |
| `method` | HTTP method |
| `path` | Request path |
| `query_params` | Query string |
| `status_code` | Response status code |
| `duration_ms` | Request processing time |
| `ip_address` | Client IP address |
| `user_agent` | Client user agent string |

### Audit Storage

| Store | Purpose | Retention |
|-------|---------|-----------|
| Firestore `audit_log` collection | Real-time queries, per-session audit | Indefinite (no TTL) |
| Cloud Storage audit bucket | Long-term archive, compliance | 7 years (Coldline after 90 days) |
| Cloud Logging | Operational monitoring | 365 days |
| Cloud Audit Logs | GCP API-level audit (automatic, tamper-evident) | 400 days (Admin Activity), configurable (Data Access) |
| VPC Flow Logs | Network-level audit | 365 days |

### Audit Trail Integrity

- Firestore data is encrypted with Google-managed or Cloud KMS keys.
- Cloud Storage audit bucket has Object Versioning enabled (preventing silent modification of archived logs).
- Cloud Storage bucket has uniform bucket-level access (no per-object ACLs).
- Cloud Storage bucket policy denies unencrypted uploads and non-HTTPS requests.
- Cloud Audit Logs are automatically generated by GCP and are tamper-evident (Google-managed, cannot be deleted by customers).

### Negotiation Audit Log

The in-application negotiation log is redacted before it leaves the process. The redacted version contains:

| Field | Included | Redacted |
|-------|----------|----------|
| Round number | Yes | - |
| Timestamp | Yes | - |
| Action type (proposal/accept/counter/reject) | Yes | - |
| Party identifier | Yes | - |
| Actual price | No | Replaced with boolean `price_offered` |
| Deal terms | No | Replaced with boolean `terms_included` |
| Rationale text | No | Stripped |
| Disclosed fields content | No | Stripped |

This ensures that the audit trail proves that the protocol executed correctly (correct turn order, round counts, outcome) without revealing any confidential negotiation content.
