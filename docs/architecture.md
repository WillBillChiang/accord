# Accord System Architecture

## Overview

Accord is a Trusted Execution Environment (TEE)-based AI negotiation engine that enables two parties to negotiate through AI agents without revealing their confidential constraints to each other or to any intermediary. The system is built on the NDAI framework (arXiv:2502.07924) and implements Conditional Recall (arXiv:2510.21904) for provable data deletion.

The core insight is that a GCP Confidential VM provides a hardware-encrypted execution environment where both parties' confidential data can coexist temporarily, AI agents can negotiate on their behalf, and all data is provably destroyed when the session ends. The entire VM is the TEE -- there is no parent/enclave split. All application components (API server, negotiation engine, LLM inference) run within a single unified process inside the Confidential VM, communicating via direct function calls.

## Data Flow Diagram

```
                                   INTERNET
                                      |
                              +-------+-------+
                              |  Cloud DNS    |
                              +-------+-------+
                                      |
                     +----------------+----------------+
                     |                                 |
              +------+------+                   +------+------+
              |  Firebase   |                   | Cloud Load  |
              |  Hosting    |                   | Balancer    |
              |  (Next.js)  |                   | + Cloud     |
              +--------------+                  | Armor (WAF) |
                                                +------+------+
                                                       |
                                          +------------+------------+
                                          |   Confidential VM       |
                                          |   (AMD SEV-SNP)         |
                                          |   GPU: NVIDIA H100/L4   |
                                          |                         |
                                          |  +-------------------+  |
                                          |  | Unified App       |  |
                                          |  | (FastAPI/uvicorn) |  |
                                          |  |                   |  |
                                          |  | - Auth middleware  |  |
                                          |  |   (Firebase Auth) |  |
                                          |  | - Audit middleware |  |
                                          |  | - Rate limiter    |  |
                                          |  | - WebSocket mgr   |  |
                                          |  | - Session mgr     |  |
                                          |  | - SAO Protocol    |  |
                                          |  | - ZOPA engine     |  |
                                          |  | - Nash Bargaining |  |
                                          |  | - LLM (GPU)      |  |
                                          |  | - KMS client      |  |
                                          |  | - Crypto (AES-GCM)|  |
                                          |  | - Secure delete   |  |
                                          |  +-------------------+  |
                                          |  ALL VM MEMORY IS       |
                                          |  HARDWARE-ENCRYPTED     |
                                          |  (AMD SEV-SNP)          |
                                          +===========+===========+=+
                                                      |
                                         (Private Google Access)
                                                      |
                                         +------------+------------+
                                         |            |            |
                                  +------+------+ +---+----+ +----+------+
                                  | Cloud KMS   | |Firestore| |  Cloud   |
                                  | (IAM-bound) | |(Native) | | Storage  |
                                  +-------------+ +---------+ +----------+
```

## Component Descriptions

### Frontend (Next.js on Firebase Hosting)

The web application provides the user interface for session management, agent configuration, attestation verification, and real-time negotiation monitoring.

| Aspect | Detail |
|--------|--------|
| Framework | Next.js (React) |
| Hosting | Firebase Hosting |
| Auth | Firebase Auth (email/password + TOTP MFA) |
| API Communication | REST (fetch) + WebSocket |
| Source | `frontend/src/` |

Key responsibilities:
- User authentication (sign-up, sign-in, MFA)
- Session creation and management dashboard
- Agent configuration form (role, constraints, disclosure policy, strategy)
- Client-side encryption of confidential data with Cloud KMS before submission
- Attestation verification UI (compare image digest and SEV-SNP status against published values)
- Real-time negotiation progress via WebSocket
- Audit log viewer

### Unified Application (FastAPI on Confidential VM)

The entire application runs as a single unified process inside a GCP Confidential VM. Unlike the previous architecture (which split the application between a parent EC2 host and a Nitro Enclave connected via vsock), the Confidential VM architecture runs all components -- API server, negotiation engine, LLM inference -- within one process. The AMD SEV-SNP technology encrypts all VM memory at the hardware level.

| Aspect | Detail |
|--------|--------|
| Framework | FastAPI + uvicorn |
| Language | Python 3.11+ |
| Auth | Firebase Auth ID token verification middleware |
| TEE | GCP Confidential VM (AMD SEV-SNP) |
| GPU | NVIDIA H100 or L4 with confidential computing support |
| Source | `app/` |

Key responsibilities:
- TLS termination (via Cloud Load Balancer) and request routing
- Firebase Auth ID token verification
- Audit log creation for every API request
- Rate limiting (sliding window, 60 req/min per IP)
- Session metadata CRUD in Firestore
- Session lifecycle management (create, onboard, negotiate, terminate)
- Cloud KMS decryption of party configurations (IAM-bound to Confidential VM service account)
- ZOPA (Zone of Possible Agreement) computation
- SAO (Stacked Alternating Offers) protocol execution
- LLM-powered proposal generation with preflight constraint enforcement (GPU-accelerated)
- Nash Bargaining Solution computation (fallback)
- Ephemeral session key management (AES-256-GCM)
- Provable data deletion (cryptographic zeroing + VM termination)
- Attestation reporting via GCE metadata service
- WebSocket management for real-time updates

**Security invariant**: The unified application runs entirely within the Confidential VM. All VM memory is hardware-encrypted by AMD SEV-SNP. The cloud provider (Google) cannot read VM memory contents. Confidential payloads are encrypted client-side with the Cloud KMS key and decrypted only within the Confidential VM using IAM-bound Cloud KMS access.

### Infrastructure (Terraform)

Five Terraform modules define the complete GCP infrastructure.

| Module | Directory | Resources |
|--------|-----------|-----------|
| Network | `infrastructure/modules/network/` | VPC, subnets, Cloud NAT, Cloud Router, firewall rules, Private Google Access |
| Security | `infrastructure/modules/security/` | Cloud KMS keyring and key (IAM-conditioned), service accounts, Cloud Armor security policy |
| Data | `infrastructure/modules/data/` | Firestore database (Native Mode), Cloud Storage buckets (audit logs, documents) |
| Compute | `infrastructure/modules/compute/` | Confidential VM instance template (SEV-SNP + GPU), Managed Instance Group (MIG), Cloud Load Balancer, health checks |
| Monitoring | `infrastructure/modules/monitoring/` | Cloud Monitoring dashboards, alerting policies, Cloud Audit Logs sinks, uptime checks |

## Data Flow

### End-to-End Negotiation Flow

1. **Authentication**: User signs in via Firebase Auth (email/password + TOTP MFA). Frontend receives a Firebase ID token.

2. **Session Creation**: Frontend calls `POST /api/v1/sessions`. The application creates a session in memory and stores metadata in Firestore.

3. **Attestation Verification**: Before submitting data, each party calls `GET /api/v1/attestation` to retrieve the container image digest, SEV-SNP status, and VM identity. They compare these against published values. This proves the Confidential VM is running the exact published code with memory encryption active.

4. **Client-Side Encryption**: The party encrypts their configuration (budget cap, reservation price, disclosure policy, strategy notes, confidential data) using the Accord Cloud KMS key. Only the Confidential VM's service account can decrypt this.

5. **Onboarding**: Party calls `POST /api/v1/sessions/{id}/onboard` with encrypted config. The application decrypts using Cloud KMS (IAM-bound to the Confidential VM service account) and stores the plaintext in memory.

6. **Negotiation Start**: When both parties are onboarded, `POST /api/v1/sessions/{id}/start` triggers the protocol:
   - **ZOPA Check**: Application computes whether seller's minimum <= buyer's maximum (result is boolean only -- actual values never revealed)
   - **SAO Protocol**: Seller agent makes opening offer. Buyer evaluates (accept/counter/reject). Alternates up to max rounds.
   - **Nash Fallback**: If SAO exhausts rounds without agreement, Nash Bargaining Solution is computed using both parties' private reservation prices.

7. **Proposal Generation**: Each proposal passes through:
   - LLM generates candidate proposal (GPU-accelerated inference inside the Confidential VM)
   - Preflight check enforces hard constraints (budget cap, concession rate, disclosure boundaries, round limit)
   - If preflight fails, LLM retries up to 3 times, then falls back to rule-based strategy

8. **Termination**: When negotiation concludes (deal, no-deal, timeout, or error):
   - Outcome is returned to the caller
   - Session keys are cryptographically zeroed (AES key overwritten with zeros)
   - All party configs and logs are recursively zeroed in memory
   - Session object is deleted
   - On VM termination, AMD SEV-SNP destroys the memory encryption key, rendering all VM memory irrecoverable

9. **Audit**: Every API request is logged with user identity, action, timestamp, and outcome. Negotiation logs are redacted (prices and terms stripped) before being written to Firestore.

## Security Model Overview

| Layer | Mechanism |
|-------|-----------|
| Transport | TLS 1.2+ (Cloud Load Balancer termination), Cloud Armor |
| Authentication | Firebase Auth ID tokens with TOTP MFA |
| Authorization | ID token claims + custom claims for role-based access |
| Data at Rest | Cloud KMS encryption (Firestore, Cloud Storage) |
| Data in Confidential VM | IAM-bound Cloud KMS decryption within Confidential VM |
| Confidential Isolation | Confidential VM (AMD SEV-SNP: all VM memory hardware-encrypted) |
| Provable Deletion | Cryptographic zeroing + SEV-SNP key destruction on VM termination |
| Side-Channel Resistance | Timing normalization, SEV-SNP memory encryption |
| Network Isolation | VPC firewall rules restrict egress to Google APIs only; Private Google Access |
| Audit | Per-request audit log, VPC Flow Logs, Cloud Audit Logs |

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend | Next.js (React) | Latest |
| API | FastAPI + uvicorn | 0.115+ |
| Runtime | Python 3.11 on Debian/Ubuntu | 3.11 |
| LLM Inference | llama-cpp-python (GPU) or vLLM | Latest |
| Schema Validation | Pydantic | 2.10.x |
| Encryption | cryptography (AES-GCM) | 44.0.x |
| Attestation | GCE metadata service (OIDC tokens with SEV-SNP claims) | - |
| Auth | firebase-admin (ID token verification) | 6.x |
| HTTP Client | httpx | 0.27.x |
| Database | Google Cloud Firestore (Native Mode) | - |
| Key Management | Google Cloud KMS | - |
| Identity | Firebase Auth | - |
| WAF | Cloud Armor | - |
| Load Balancing | Cloud Load Balancer (HTTPS) | - |
| Infrastructure | Terraform | >= 1.5 |
| Container Registry | Artifact Registry | - |
| Monitoring | Cloud Monitoring + Cloud Logging | - |

## Deployment Topology

```
Region: us-central1
|
+-- VPC (10.0.0.0/16)
    |
    +-- Public Subnet (10.0.1.0/24)
    |   +-- Cloud NAT (outbound internet for container pulls)
    |   +-- Cloud Load Balancer (public-facing, HTTPS)
    |
    +-- Private Subnet (10.0.10.0/24)
    |   +-- Confidential VM (MIG, SEV-SNP + GPU)
    |   +-- Private Google Access enabled
    |
    +-- Firewall Rules
        +-- Allow: HTTPS from Load Balancer to Confidential VM
        +-- Allow: Egress to Google APIs (restricted.googleapis.com)
        +-- Deny: All other egress (no public internet from VM)
        +-- Allow: Health check probes from Google health checkers
```

All Google Cloud service traffic (Firestore, Cloud Storage, Cloud KMS, Cloud Logging) flows over Private Google Access, staying within Google's network. The Confidential VM is in a private subnet with no public IP address. VPC firewall rules restrict egress to Google APIs only -- the VM cannot reach the public internet. This compensates for the fact that Confidential VMs (unlike Nitro Enclaves) have network access: the VM has a network interface, but firewall rules ensure it can only communicate with Google services and the load balancer.
