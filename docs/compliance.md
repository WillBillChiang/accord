# Accord Compliance Documentation

## Overview

Accord is designed to meet SOC 2 Type II and ISO 27001 compliance requirements. This document maps each control criterion to Accord's specific implementation, identifies the evidence artifacts, and designates the responsible party.

The Confidential VM architecture provides unique advantages for compliance: hardware-enforced memory encryption guarantees (AMD SEV-SNP), attestation-based identity verification, provable data deletion, and comprehensive audit trails through GCP's native Cloud Audit Logs.

---

## SOC 2 Type II Trust Service Criteria

### CC1: Control Environment -- Organization and Management

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC1.1 | The entity demonstrates a commitment to integrity and ethical values | Security-first architecture documented in code and architecture docs. All application code is open-source and auditable. | Source code repository, architecture documentation, code review history | Engineering Lead |
| CC1.2 | The board of directors demonstrates independence from management | Separation of operational roles: cloud provider cannot access Confidential VM memory (SEV-SNP); Firebase Auth admin custom claims are audited via Cloud Audit Logs | IAM policies, Firebase Auth custom claims, Cloud Audit Logs | Security Officer |
| CC1.3 | Management establishes structures, reporting lines, and authorities | RBAC via Firebase Auth custom claims (user, admin). API authorization enforced per-endpoint. IAM roles follow least privilege. | Firebase Auth config, IAM role policies (Terraform modules), middleware code (`auth.py`) | Security Officer |
| CC1.4 | The entity demonstrates commitment to attract, develop, and retain competent individuals | (Organizational policy -- outside system scope) | HR policies, training records | HR |
| CC1.5 | The entity holds individuals accountable for their internal control responsibilities | Per-request audit logging with user identity. All API actions traced to authenticated Firebase users. | Audit log entries in Firestore, Cloud Logging | Security Officer |

### CC2: Communication and Information

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC2.1 | The entity obtains or generates and uses relevant, quality information | Real-time session status from the Confidential VM. Structured audit logs with timestamp, user, action, outcome. | Firestore audit collection schema, audit middleware (`audit.py`) | Engineering Lead |
| CC2.2 | The entity internally communicates information | Cloud Monitoring dashboards for system health. Audit logs accessible to admin role. WebSocket for real-time updates. | Cloud Monitoring dashboards, WebSocket manager (`websocket_manager.py`), admin audit API (`audit.py`) | Operations |
| CC2.3 | The entity communicates with external parties | Attestation endpoint publicly accessible for verification. Image digest and SEV-SNP status published for independent audit. API documentation (OpenAPI) available at `/docs`. | Attestation API (`attestation.py`), published image digests, OpenAPI spec | Engineering Lead |

### CC3: Risk Assessment

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC3.1 | The entity specifies objectives with clarity | System designed to protect confidential negotiation data. Security objectives documented in `security-model.md`. | Security model documentation, threat model | Security Officer |
| CC3.2 | The entity identifies risks to the achievement of its objectives | Threat model identifies: insider threats, data exfiltration, side-channel attacks, credential theft, DDoS, network egress. Each risk has documented mitigations. | Threat model in `security-model.md`, Cloud Armor config (Terraform) | Security Officer |
| CC3.3 | The entity considers the potential for fraud | Platform operator isolation: AMD SEV-SNP prevents even Google from reading VM memory. Code is auditable. Attestation verifiable. | Confidential VM architecture, Cloud KMS IAM binding, open-source code | Security Officer |
| CC3.4 | The entity identifies and assesses changes that could significantly impact the system | Container image changes produce new digests, requiring publication and verification. Terraform plan reviews before deployment. | Image digest tracking, Terraform plan output, deployment procedures | Engineering Lead |

### CC4: Monitoring Activities

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC4.1 | The entity selects, develops, and performs ongoing evaluations | Per-request audit logging. VPC Flow Logs. Cloud Audit Logs for GCP API calls. Cloud Armor request logging. | Firestore audit collection, Cloud Logging log sinks, Cloud Audit Logs, VPC Flow Log config (Terraform) | Operations |
| CC4.2 | The entity evaluates and communicates internal control deficiencies | Cloud KMS access failures logged in Cloud Audit Logs (indicates unauthorized access). Rate limit violations logged. Error responses tracked. | Cloud Audit Logs, Cloud Armor metrics, application error logs | Security Officer |

### CC5: Control Activities

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC5.1 | The entity selects and develops control activities | Defense-in-depth: TLS, Cloud Armor, Firebase Auth MFA, ID token validation, rate limiting, Confidential VM (SEV-SNP), Cloud KMS IAM, preflight constraints, provable deletion. | Terraform modules, middleware code, application code | Engineering Lead |
| CC5.2 | The entity deploys control activities through policies and procedures | Deployment procedures documented. Terraform enforces consistent infrastructure. Automated security controls (Cloud Armor, MFA, encryption). | Deployment guide, Terraform modules, `security` module | Operations |
| CC5.3 | The entity deploys controls using technology | Automated: Firebase ID token verification middleware, rate limiting middleware, audit logging middleware, Cloud Armor rules, Cloud KMS IAM conditions, preflight constraint enforcement. | `auth.py`, `rate_limit.py`, `audit.py`, Terraform `security` module, `preflight.py` | Engineering Lead |

### CC6: Logical and Physical Access Controls

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC6.1 | The entity implements logical access security over protected information assets | Firebase Auth with required TOTP MFA. ID tokens validated on every request. Admin custom claim for elevated access. | Firebase Auth config (TOTP MFA), `auth.py` (ID token validation), custom claims | Security Officer |
| CC6.2 | Prior to issuing system credentials, the entity registers and authorizes new users | Firebase Auth user registration with email verification. Admin-created users receive temporary passwords. | Firebase Auth configuration | Security Officer |
| CC6.3 | The entity authorizes, modifies, or removes access based on authorization | Firebase Auth admin manages user accounts. ID token claims determine access level per request. Session-based access to negotiation data. | Firebase Admin SDK, authorization checks in route handlers | Security Officer |
| CC6.4 | The entity restricts physical access to facilities and protected assets | Confidential VM in private subnet with no public IP. VM memory encrypted by AMD SEV-SNP. GCP data center physical security (GCP SOC 2 report). | VPC config (Terraform `network` module), Confidential VM config, GCP SOC 2 report | GCP (shared responsibility) |
| CC6.5 | The entity discontinues logical access | Firebase Auth user disable/delete. ID tokens expire after 1 hour. Session termination provably destroys data. | Firebase Admin SDK, token validity, session termination code (`session.py`) | Security Officer |
| CC6.6 | The entity manages system boundary protections | VPC with firewall rules restricting egress to Google APIs only. Cloud Armor on Load Balancer. Private Google Access for service traffic. Confidential VM encrypts all memory. | Terraform `network` module, Terraform `security` module (Cloud Armor), firewall rules | Engineering Lead |
| CC6.7 | The entity restricts transmission, movement, and removal of information | Confidential VM egress restricted to Google APIs. All data encrypted in transit (TLS) and at rest (Cloud KMS). NEVER_DISCLOSE fields blocked by preflight. Confidential data never written to disk. | VPC firewall rules, `preflight.py` (disclosure enforcement), Cloud KMS encryption config | Engineering Lead |
| CC6.8 | The entity implements controls to prevent or detect unauthorized or malicious software | Container image verified by digest. Shielded VM Secure Boot prevents boot-level tampering. Cloud Armor blocks common exploits. | Image digest verification, Shielded VM config, Cloud Armor rules (Terraform) | Engineering Lead |

### CC7: System Operations

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC7.1 | To meet its objectives, the entity uses detection and monitoring procedures | Load Balancer health checks. Per-request audit logging. Cloud Monitoring metrics. VPC Flow Logs. Cloud Armor request logging. | LB health check (`/health`), audit middleware, Cloud Monitoring, VPC Flow Logs | Operations |
| CC7.2 | The entity monitors system components for anomalies | Cloud Audit Logs monitors KMS usage (detects unauthorized decrypt attempts). Cloud Armor rate limiting detects abuse. Application rate limiter detects per-IP abuse. | Cloud Audit Logs, Cloud Armor metrics, `rate_limit.py` | Operations |
| CC7.3 | The entity evaluates security events | Audit logs queryable by session, user, time range. Admin API provides cross-session audit view. | Audit API endpoints (`audit.py`), Firestore audit collection | Security Officer |
| CC7.4 | The entity responds to identified security events | Confidential VM terminable via MIG (immediate SEV-SNP key destruction). Sessions terminable via API. User accounts disableable via Firebase Auth. | MIG management commands, `DELETE /sessions/{id}`, Firebase Admin SDK | Security Officer |
| CC7.5 | The entity identifies, develops, and implements activities to recover from events | Disaster recovery procedures documented. Firestore has Point-in-Time Recovery. Cloud Storage versioning. Terraform redeploy for full recovery. | Confidential VM operations guide (disaster recovery section), Firestore PITR config | Operations |

### CC8: Change Management

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC8.1 | The entity authorizes, designs, develops, configures, documents, tests, approves, and implements changes | Container image changes produce new digests, requiring publication (explicit approval step). Terraform plan reviewed before apply. | Image digest tracking, Terraform plan output, deployment guide | Engineering Lead |

### CC9: Risk Mitigation

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| CC9.1 | The entity identifies, selects, and develops risk mitigation activities | Multi-layer security: Cloud Armor, MFA, ID tokens, encryption, Confidential VM (SEV-SNP), preflight enforcement, provable deletion, VPC firewall egress control. Each addresses specific threats. | Threat model, security architecture, implementation code | Security Officer |
| CC9.2 | The entity assesses and manages risks associated with vendors and business partners | GCP shared responsibility model. Cloud KMS IAM binding ensures only the Confidential VM service account can decrypt. AMD SEV-SNP prevents GCP from reading VM memory. | GCP SOC 2 report, Cloud KMS IAM policy (Terraform), SEV-SNP documentation | Security Officer |

### A1: Availability

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| A1.1 | The entity maintains, monitors, and evaluates current capacity | Confidential VM machine type sizing. GPU allocation. Firestore auto-scaling. Cloud Monitoring capacity dashboards. | Instance template config, Terraform `compute` module | Operations |
| A1.2 | The entity authorizes, designs, develops, implements, operates, approves, maintains, and monitors environmental protections | GCP data center environmental controls. Managed Instance Group for automatic VM recovery. Cloud NAT for outbound resilience. | Terraform `compute` module (MIG config), GCP SOC 2 report | GCP / Operations |
| A1.3 | The entity tests recovery plan procedures | Disaster recovery procedures documented and testable. Firestore PITR restoration tested periodically. Terraform redeploy tested. | DR test records, PITR restoration tests, Terraform plan tests | Operations |

### C1: Confidentiality

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| C1.1 | The entity identifies and maintains confidential information | Confidential data classified: party configs, reservation prices, strategy notes, confidential_data dict. All exist only in Confidential VM memory (hardware-encrypted by SEV-SNP). | Data classification in `schemas.py`, Terraform resource labels | Security Officer |
| C1.2 | The entity disposes of confidential information | Provable deletion: cryptographic zeroing of keys, recursive zeroing of data structures, SEV-SNP memory key destruction on VM termination. | `secure_delete.py`, `session_keys.py` (destroy method), `session.py` (_destroy_session_data) | Engineering Lead |

### PI1: Processing Integrity

| Control | Description | Accord Implementation | Evidence / Artifacts | Responsible |
|---------|-------------|----------------------|---------------------|-------------|
| PI1.1 | The entity uses quality information to support the functioning of internal controls | Pydantic schema validation on all API inputs and internal data structures. Type checking on all protocol parameters. | `schemas.py` (Pydantic models), route request models, field validators | Engineering Lead |
| PI1.2 | The entity implements policies and procedures over system inputs | Input validation: role must be "seller"/"buyer", budget_cap > 0, max_rounds 1-50, max_concession_per_round 0.01-1.0. Preflight enforces constraints on LLM output. | Pydantic validators in `schemas.py`, preflight checks in `preflight.py` | Engineering Lead |
| PI1.3 | The entity implements policies and procedures over system processing | SAO protocol enforces turn order, round limits, budget caps, concession rates, and disclosure boundaries. All enforced in code, not LLM prompts. | `sao.py` (protocol engine), `preflight.py` (constraint enforcement) | Engineering Lead |
| PI1.4 | The entity implements policies and procedures to make corrections | Preflight retry loop: if LLM generates violating proposal, it retries up to 3 times, then falls back to safe rule-based proposal. | `base_agent.py` (generate_proposal retry loop, fallback) | Engineering Lead |
| PI1.5 | The entity implements policies and procedures over outputs | Negotiation log redacted before leaving the application (prices, terms, rationale stripped). Only boolean indicators returned. | `session.py` (get_redacted_log method) | Engineering Lead |

---

## ISO 27001:2022 Annex A Control Mapping

### A.5: Organizational Controls

| Control | Title | Accord Implementation | Evidence |
|---------|-------|----------------------|----------|
| A.5.1 | Policies for information security | Security model documented. Architecture enforces confidentiality by design. | `security-model.md`, `architecture.md` |
| A.5.2 | Information security roles and responsibilities | Service accounts with least-privilege IAM. Firebase Auth custom claims (user, admin). | Terraform `security` module (service accounts), Firebase Auth config |
| A.5.3 | Segregation of duties | Application in Confidential VM -- even cloud provider cannot read memory. Admins view audit logs but not negotiation content. | Cloud KMS IAM binding, SEV-SNP, audit API authorization |
| A.5.7 | Threat intelligence | Cloud Armor uses Google-managed IP reputation rules. Rate limiting detects abuse patterns. | Terraform `security` module (Cloud Armor rules) |
| A.5.8 | Information security in project management | Security controls embedded in architecture (not bolted on). Confidential VM is foundational design decision. | Architecture documentation |
| A.5.9 | Inventory of information and other associated assets | Firestore collections tracked via Terraform. Cloud Storage buckets inventoried. Cloud KMS keys tracked. | Terraform state, `terraform output` |
| A.5.10 | Acceptable use of information | Disclosure tiers (MUST/MAY/NEVER) define acceptable use of each data field per party's instructions. | `schemas.py` (DisclosureTier), `preflight.py` |
| A.5.12 | Classification of information | Data tagged by classification: PII (user data in Firebase Auth), confidential (audit logs, documents), internal (session metadata). | Terraform resource labels |
| A.5.13 | Labeling of information | Cloud Storage and Firestore resources labeled with data_classification and retention_policy. | Terraform resource labels |
| A.5.14 | Information transfer | All external transfers over TLS. Confidential data encrypted with Cloud KMS before transfer. | Cloud Load Balancer TLS config, Cloud KMS encryption workflow |
| A.5.15 | Access control | Firebase Auth + ID token authorization. Cloud KMS IAM-bound decryption. Confidential VM restricts egress. | `auth.py`, Terraform `security` module (Cloud KMS IAM) |
| A.5.23 | Information security for cloud services | Private Google Access keeps traffic off public internet. Private subnet for compute. Cloud KMS encryption for all data stores. | Terraform `network` module (Private Google Access), Terraform `data` module (encryption) |
| A.5.24 | Information security incident management | Confidential VM terminable via MIG for immediate SEV-SNP key destruction. Audit logs preserved for investigation. | MIG termination procedures, audit log retention |
| A.5.28 | Collection of evidence | Comprehensive audit trail: per-request Firestore logs, VPC Flow Logs, Cloud Audit Logs (automatic). Cloud Storage Object Versioning prevents tampering. | Audit infrastructure (Terraform `data` and `monitoring` modules, `audit.py`) |
| A.5.29 | Information security during disruption | Firestore PITR for data recovery. Cloud Storage versioning. Documented disaster recovery procedures. | Firestore PITR config, DR procedures in operations guide |
| A.5.30 | ICT readiness for business continuity | MIG with autohealing for automatic VM recovery. Firestore auto-scaling. Terraform redeploy for full recovery. | Terraform `compute` module (MIG autohealing), Terraform state |
| A.5.33 | Protection of records | Audit logs retained indefinitely in Firestore (no TTL). Cloud Storage audit logs retained 7 years with lifecycle policy. Cloud Audit Logs retained per GCP policy (400 days Admin Activity). | Firestore config (no TTL), Cloud Storage lifecycle policy (Terraform) |
| A.5.34 | Privacy and protection of PII | Confidential data exists only in Confidential VM memory (hardware-encrypted). Session keys destroyed after use. User PII in Firebase Auth (managed by Google). | Confidential VM architecture, `secure_delete.py`, Firebase Auth |
| A.5.36 | Compliance with policies, rules, and standards | This compliance document. Automated controls enforced via code and Terraform modules. | This document, Terraform modules |

### A.6: People Controls

| Control | Title | Accord Implementation | Evidence |
|---------|-------|----------------------|----------|
| A.6.1 | Screening | (Organizational policy) | HR records |
| A.6.2 | Terms and conditions of employment | (Organizational policy) | Employment agreements |
| A.6.3 | Information security awareness, education, and training | (Organizational policy) | Training records |
| A.6.4 | Disciplinary process | (Organizational policy) | HR policies |
| A.6.5 | Responsibilities after termination | Firebase Auth user disable/delete removes access immediately. ID tokens expire within 1 hour. | Firebase Admin SDK, token expiry config |

### A.7: Physical Controls

| Control | Title | Accord Implementation | Evidence |
|---------|-------|----------------------|----------|
| A.7.1 | Physical security perimeters | GCP data center physical security (shared responsibility). | GCP SOC 2 report |
| A.7.2 | Physical entry | GCP data center access controls (shared responsibility). | GCP SOC 2 report |
| A.7.4 | Physical security monitoring | GCP data center monitoring (shared responsibility). | GCP SOC 2 report |
| A.7.9 | Security of assets off-premises | No Accord data stored off-premises. All data in GCP. | Architecture documentation |
| A.7.10 | Storage media | Encrypted boot disks (Cloud KMS). Firestore server-side encryption. Cloud Storage server-side encryption. No unencrypted storage. | Terraform `compute` module (encrypted disks), Terraform `data` module (encryption config) |
| A.7.14 | Secure disposal or re-use of equipment | Provable deletion in application (cryptographic zeroing). SEV-SNP key destruction on VM termination. GCP handles hardware disposal (shared responsibility). | `secure_delete.py`, `session_keys.py`, GCP data disposal policy |

### A.8: Technological Controls

| Control | Title | Accord Implementation | Evidence |
|---------|-------|----------------------|----------|
| A.8.1 | User endpoint devices | Client-side encryption before data submission. MFA required (TOTP). | Cloud KMS client-side encryption workflow, Firebase Auth MFA config |
| A.8.2 | Privileged access rights | Admin Firebase Auth custom claim for elevated access. Service accounts use least-privilege IAM. Root account not used for operations. | Firebase Auth custom claims, Terraform `security` module (IAM policies) |
| A.8.3 | Information access restriction | ZOPA check returns boolean only. Negotiation log is redacted before leaving the application. NEVER_DISCLOSE fields hard-blocked. | `zopa.py`, `session.py` (get_redacted_log), `preflight.py` |
| A.8.4 | Access to source code | Application source code is open-source for audit. Infrastructure as code in version control. | Git repository, open-source license |
| A.8.5 | Secure authentication | Firebase Auth email/password (password never stored in plaintext). TOTP MFA required. RS256 ID token signatures. | Firebase Auth config, `auth.py` (ID token verification) |
| A.8.6 | Capacity management | Firestore auto-scaling. Confidential VM sizing for workload. GPU allocation configurable. | Terraform `compute` module, instance template config |
| A.8.7 | Protection against malware | Container image verified by digest. Shielded VM Secure Boot prevents boot-level tampering. Cloud Armor blocks common exploits. | Image digest verification, Shielded VM config, Cloud Armor rules |
| A.8.8 | Management of technical vulnerabilities | Dependencies pinned to specific versions. Container rebuilt with updated packages. Image digest changes on any update. | `Dockerfile` (pinned versions), image digest tracking |
| A.8.9 | Configuration management | Terraform for infrastructure (version-controlled, repeatable). Environment variables for runtime config (via Secret Manager or instance metadata). | Terraform modules, environment variable documentation |
| A.8.10 | Information deletion | Provable deletion via cryptographic zeroing + SEV-SNP key destruction on VM termination. Cloud Storage lifecycle policies for retention then deletion. | `secure_delete.py`, `session.py`, Terraform `data` module (lifecycle rules) |
| A.8.11 | Data masking | Negotiation log redacted (prices/terms replaced with booleans). Confidential data never stored outside Confidential VM memory. | `session.py` (get_redacted_log) |
| A.8.12 | Data leakage prevention | Confidential VM egress restricted to Google APIs only (VPC firewall). NEVER_DISCLOSE fields blocked by preflight. Confidential data never written to disk. | VPC firewall rules (Terraform), `preflight.py` |
| A.8.15 | Logging | Per-request audit log with user, action, timestamp, outcome. VPC Flow Logs. Cloud Audit Logs (automatic). Cloud Logging application logs. | `audit.py`, Terraform `network` module (Flow Logs), Cloud Audit Logs |
| A.8.16 | Monitoring activities | Cloud Monitoring dashboards and alerting. Cloud Armor metrics. Load Balancer metrics. Application error logging. | Terraform `monitoring` module |
| A.8.20 | Networks security | VPC with firewall rules restricting egress to Google APIs. Private subnet for Confidential VM. Private Google Access for service traffic. | Terraform `network` module |
| A.8.21 | Security of network services | TLS 1.2+ on Cloud Load Balancer. Private Google Access for internal service traffic. No public internet from VM. | Cloud LB TLS config, Terraform `network` module |
| A.8.22 | Segregation of networks | Public subnet (Load Balancer only). Private subnet (Confidential VM). VPC firewall denies egress except to Google APIs. | Terraform `network` module (subnet and firewall architecture) |
| A.8.23 | Web filtering | Cloud Armor with Google-managed rules (OWASP Top 10, IP reputation). Application rate limiting. | Terraform `security` module (Cloud Armor config), `rate_limit.py` |
| A.8.24 | Use of cryptography | AES-256-GCM for session encryption. Cloud KMS for data at rest. AMD SEV-SNP for memory encryption. TLS for transit. | `session_keys.py`, Terraform `data` module (Cloud KMS), Confidential VM config |
| A.8.25 | Secure development lifecycle | Preflight enforcement separates LLM output from hard constraints. Pydantic validation on all inputs. | `preflight.py`, `schemas.py` |
| A.8.26 | Application security requirements | Authentication required on all protected endpoints. Input validation. Rate limiting. CORS configuration. | `auth.py`, `rate_limit.py`, `server.py` (CORS) |
| A.8.28 | Secure coding | Application code handles all exceptions. Fallback strategies for LLM failures. Secure memory zeroing. No SQL (Firestore NoSQL only). | Error handling in `main.py`, fallback in `base_agent.py`, `secure_delete.py` |

---

## Compliance Evidence Summary

| Evidence Type | Location | Retention |
|---------------|----------|-----------|
| Audit logs (per-request) | Firestore `audit_log` collection | Indefinite |
| Audit logs (archive) | Cloud Storage `accord-audit-logs` bucket | 7 years (Object Versioning) |
| VPC Flow Logs | Cloud Logging | 365 days |
| Cloud Audit Logs (Admin Activity) | Cloud Logging (automatic) | 400 days (GCP-managed) |
| Cloud Audit Logs (Data Access) | Cloud Logging (configurable) | Configurable |
| Infrastructure definitions | Terraform modules (Git) | Git history |
| Application code | Git repository | Git history |
| Container image digests | Artifact Registry + Secret Manager + Git | Version history |
| Cloud KMS key usage | Cloud Audit Logs | 400 days |
| Firebase Auth events | Cloud Logging | Configurable |
| Cloud Armor logs | Cloud Logging | Configurable |

---

## Shared Responsibility

| Control Area | GCP Responsibility | Accord Responsibility |
|-------------|-------------------|----------------------|
| Physical security | Data center access, environmental controls | N/A |
| Hypervisor security | Compute Engine hypervisor | Configure Confidential VM correctly |
| Hardware memory encryption | AMD SEV-SNP silicon implementation | Enable Confidential VM, verify attestation |
| Network infrastructure | Global network, DDoS baseline | VPC firewall rules, Cloud Armor rules |
| KMS key security | HSM operations, key storage | IAM policies, service account bindings |
| Confidential VM attestation | GCE metadata service, Shielded VM infrastructure | Correct image build, digest verification, attestation checking |
| Data encryption | Cloud KMS / SSE implementation | Encryption configuration, key management |
| Identity management | Firebase Auth service operation | Auth configuration, MFA policy, custom claims |
| Application security | N/A | Code, preflight enforcement, secure deletion |
