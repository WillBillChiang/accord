# GCP Confidential Computing for Accord

**Document Classification**: Internal -- Security Architecture
**Compliance Scope**: SOC 2 Type II (CC6.4, CC6.6, CC6.7, CC9.2), ISO 27001 (A.5.3, A.5.23, A.8.24, A.7.14)
**Last Updated**: 2026-03-11
**Owner**: Security Officer / Engineering Lead

---

## Table of Contents

1. [Overview](#overview)
2. [How Confidential VMs Differ from Nitro Enclaves](#how-confidential-vms-differ-from-nitro-enclaves)
3. [Security Model](#security-model)
4. [Attestation](#attestation)
5. [GPU Support](#gpu-support)
6. [Trust Model Comparison](#trust-model-comparison)
7. [Compensating Controls](#compensating-controls)
8. [Operational Considerations](#operational-considerations)
9. [References](#references)

---

## Overview

### What Are GCP Confidential VMs

GCP Confidential VMs are Compute Engine virtual machines that use AMD SEV-SNP (Secure Encrypted Virtualization -- Secure Nested Paging) to encrypt all VM memory at the hardware level. The encryption is performed by a dedicated security co-processor on the AMD EPYC CPU die -- the AMD Secure Processor -- using a per-VM AES-128 encryption key that is never exposed to any software layer, including the hypervisor. This means that the cloud provider (Google), a compromised hypervisor, or an attacker with physical access to DRAM cannot read the VM's memory contents.

Key properties:

- **Hardware memory encryption**: All VM memory pages are transparently encrypted and decrypted by the CPU memory controller on every read and write.
- **Per-VM key isolation**: Each VM receives a unique encryption key generated and stored inside the AMD Secure Processor. The key is never accessible to software.
- **Integrity protection (SNP)**: SNP adds a Reverse Map Table (RMP) that prevents the hypervisor from performing replay attacks, remapping attacks, or other memory manipulation on encrypted pages.
- **Attestation**: The AMD Secure Processor generates signed launch measurements, and the GCE metadata service provides OIDC identity tokens with confidential computing claims.
- **Provable deletion**: When the VM terminates, the AMD Secure Processor destroys the per-VM encryption key, rendering all memory pages cryptographically irrecoverable.

### Why Accord Uses Confidential VMs

Accord is a TEE-based AI negotiation engine built on the NDAI framework (arXiv:2502.07924). Two parties submit their confidential negotiation constraints (reservation prices, budget caps, strategy parameters) to an AI-powered engine that negotiates on their behalf. Neither party should be able to see the other's private data, and the platform operator should not be able to see either party's data.

Accord migrated from AWS Nitro Enclaves to GCP Confidential VMs for three reasons:

1. **GPU acceleration**: Nitro Enclaves do not support GPU passthrough. LLM inference on CPU took minutes per proposal. Confidential VMs support NVIDIA H100 and L4 GPUs, reducing inference to seconds -- a requirement for production-quality negotiation sessions.

2. **Simplified architecture**: The Nitro Enclave architecture required splitting the application into a parent process (API server on EC2) and an enclave process (negotiation engine), connected by vsock with fixed-size padded messages. The Confidential VM architecture runs everything in a single unified process, eliminating the vsock relay layer, message padding, and parent/enclave synchronization complexity.

3. **Standard operational tooling**: Confidential VMs support Cloud Logging, Cloud Monitoring, and standard diagnostic workflows. The Nitro Enclave architecture required custom vsock-based log forwarding and had limited observability.

The trade-off is that Confidential VMs have network access, disk access, and (in principle) shell access -- capabilities that Nitro Enclaves lacked entirely. Accord addresses this with compensating controls documented in the [Compensating Controls](#compensating-controls) section.

---

## How Confidential VMs Differ from Nitro Enclaves

### Nitro Enclaves Architecture

AWS Nitro Enclaves create a separate, isolated virtual machine (the enclave) nested inside a parent EC2 instance. The enclave is managed by the Nitro Hypervisor and has the following hard constraints enforced by hardware and firmware:

| Property | Nitro Enclave Behavior |
|----------|------------------------|
| **Network** | No network interfaces. Zero network access. |
| **Communication** | vsock (AF_VSOCK) to the parent EC2 instance only. |
| **Disk** | No filesystem. RAM-only execution with a read-only root filesystem baked into the Enclave Image File (EIF). |
| **Shell / Debug** | No SSH, no console, no ptrace, no debug interface. Not even the EC2 instance owner can inspect enclave memory. |
| **Attestation** | PCR-based attestation via `/dev/nsm` (Nitro Security Module). PCR0 = enclave image hash, PCR1 = Linux kernel hash, PCR2 = application hash. Attestation documents are CBOR-encoded and signed by the AWS Nitro Attestation PKI. |
| **KMS integration** | AWS KMS key policies can be conditioned on PCR values. The enclave obtains decryption grants only when its measurements match the policy. KMS calls are proxied through the parent via vsock-proxy. |

In Accord's previous architecture, the application was split into two processes:
- **Parent app** (EC2): FastAPI server handling HTTP/WebSocket, authentication, audit logging.
- **Enclave app** (Nitro Enclave): Negotiation engine, LLM inference, cryptographic operations. Communicated with the parent via vsock with 64KB fixed-size padded messages.

### Confidential VM Architecture

GCP Confidential VMs take a different approach: the entire VM is the TEE. Instead of isolating a nested VM, AMD SEV-SNP encrypts all memory of the standard VM at the hardware level.

| Property | Confidential VM Behavior |
|----------|--------------------------|
| **Network** | Full network interface present. Restricted by VPC firewall rules to Google APIs only via Private Google Access. |
| **Communication** | Standard networking (HTTPS, gRPC, WebSocket). No vsock required. |
| **Disk** | Full disk access. Boot disk encrypted with Cloud KMS. Application enforces a policy of never writing confidential data to disk (RAM-only for sensitive payloads). |
| **Shell / Debug** | SSH is technically possible. Disabled in production via IAM policies and VPC firewall rules. All access attempts logged in Cloud Audit Logs. |
| **Attestation** | Image digest (SHA-256 of container image) replaces PCR0/1/2. GCE metadata service provides OIDC identity tokens with SEV-SNP attestation claims. Tokens are signed by Google. |
| **KMS integration** | Cloud KMS access is IAM-conditioned. The `cloudkms.cryptoKeyVersions.useToDecrypt` permission is restricted to the Confidential VM's service account. |

In Accord's current architecture, the application runs as a single unified process (FastAPI + uvicorn) inside the Confidential VM. All components -- API server, authentication middleware, negotiation engine, LLM inference (GPU-accelerated), and cryptographic operations -- execute within one process. All VM memory is hardware-encrypted by AMD SEV-SNP.

### Side-by-Side Architectural Diagram

```
PREVIOUS (AWS Nitro Enclaves)              CURRENT (GCP Confidential VMs)
================================           ================================

EC2 Instance (Parent)                      Confidential VM (AMD SEV-SNP)
+---------------------------+              +---------------------------+
| Parent App (FastAPI)      |              | Unified App (FastAPI)     |
|  - HTTP/WebSocket handler |              |  - HTTP/WebSocket handler |
|  - Firebase Auth          |              |  - Firebase Auth          |
|  - Audit logging          |              |  - Audit logging          |
|  - vsock relay            |              |  - Negotiation engine     |
+----------+----------------+              |  - LLM inference (GPU)    |
           | vsock (AF_VSOCK)              |  - Cloud KMS client       |
           | 64KB padded msgs              |  - Secure deletion        |
+----------+----------------+              +---------------------------+
| Nitro Enclave (isolated)  |              ALL VM MEMORY IS
|  - Negotiation engine     |              HARDWARE-ENCRYPTED
|  - LLM inference (CPU)    |              (AMD SEV-SNP)
|  - KMS client (via proxy) |
|  - Secure deletion        |
|  NO NETWORK, NO DISK      |
|  NO SHELL, NO DEBUG       |
+---------------------------+
```

---

## Security Model

### AMD SEV-SNP Hardware Memory Encryption

All VM memory is encrypted at the hardware level by the AMD Secure Processor using a per-VM AES-128 key. The encryption operates at the memory controller level -- every read from DRAM is decrypted, every write to DRAM is encrypted. This is transparent to the operating system and application.

| Property | Detail |
|----------|--------|
| **Encryption algorithm** | AES-128-XEX (Xor-Encrypt-Xor mode) in the memory controller |
| **Key management** | Per-VM key generated by AMD Secure Processor; never exposed to software |
| **Key lifecycle** | Created at VM launch, destroyed at VM termination |
| **Integrity protection** | SNP Reverse Map Table (RMP) prevents hypervisor replay, remapping, and aliasing attacks |
| **Performance overhead** | Minimal (< 5% for most workloads) due to hardware acceleration |

**Compliance mapping**: This control satisfies SOC 2 CC6.4 (physical access restrictions -- even physical DRAM access yields encrypted data), ISO 27001 A.8.24 (use of cryptography), and ISO 27001 A.5.3 (segregation of duties -- cloud provider cannot read VM memory).

### Secure Boot, vTPM, and Integrity Monitoring

Confidential VMs include all Shielded VM security features:

| Feature | Function | Compliance Relevance |
|---------|----------|---------------------|
| **Secure Boot** | Ensures the VM boots only with verified, signed firmware and bootloaders. Prevents boot-kit and rootkit attacks that could compromise the VM before the OS loads. | SOC 2 CC6.8 (unauthorized software prevention), ISO 27001 A.8.7 (malware protection) |
| **vTPM (Virtual Trusted Platform Module)** | Provides measured boot. Records the boot chain (firmware, bootloader, kernel) into platform configuration registers. Enables remote attestation of the boot state. | SOC 2 CC6.8, ISO 27001 A.8.7 |
| **Integrity Monitoring** | Compares current boot measurements against a known-good baseline established on first boot. Generates Cloud Monitoring events on any deviation, indicating potential tampering. | SOC 2 CC7.1 (detection and monitoring), ISO 27001 A.8.16 (monitoring activities) |

These three features work together to establish a verified boot chain. If any component in the boot sequence is modified (firmware, kernel, initrd), Integrity Monitoring will flag it, and Secure Boot will prevent the VM from booting if the modification is unsigned.

### Cloud KMS Bound to Confidential VM Service Account

Party data is encrypted client-side using the Accord Cloud KMS key. Decryption is restricted to the Confidential VM's service account via IAM:

```hcl
resource "google_kms_crypto_key_iam_member" "encrypter_decrypter" {
  crypto_key_id = google_kms_crypto_key.accord_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.confidential_vm.email}"
}
```

**Security properties**:

1. Any authenticated user can encrypt data with the Accord Cloud KMS key (encryption is not restricted).
2. Only the Confidential VM's service account can decrypt. A compromised external server, a different VM, or even a GCP project administrator without the service account credentials cannot decrypt party data.
3. The service account credentials are obtained automatically from the GCE metadata service and are bound to the specific VM instance.
4. Cloud Audit Logs record every KMS `Decrypt` call, including the caller identity, timestamp, and key version. Unauthorized decrypt attempts are logged and can trigger alerts.

**Compliance mapping**: SOC 2 CC6.1 (logical access controls), CC6.3 (access authorization), ISO 27001 A.5.15 (access control), A.8.2 (privileged access rights).

### Provable Deletion via Memory Encryption Key Destruction

When the Confidential VM terminates, the AMD Secure Processor destroys the per-VM encryption key. This renders all encrypted memory pages cryptographically irrecoverable -- there is no key to decrypt them with. This is the hardware foundation of Accord's provable deletion guarantee (Conditional Recall, arXiv:2510.21904).

The deletion chain is:

1. **Application-level**: Session keys cryptographically zeroed (`ctypes.memset`), party configs recursively zeroed, negotiation logs cleared.
2. **Hardware-level**: On VM termination, AMD SEV-SNP key is destroyed. All VM memory pages become irrecoverable ciphertext.

This two-layer approach ensures that confidential data is destroyed even if the application-level zeroing has a bug (the hardware key destruction is unconditional on VM termination).

**Compliance mapping**: SOC 2 C1.2 (disposal of confidential information), ISO 27001 A.5.34 (PII protection), A.7.14 (secure disposal), A.8.10 (information deletion).

### VPC Firewall Restricts Egress to Google APIs

The Confidential VM is deployed in a private subnet with no public IP address. VPC firewall rules enforce:

| Rule | Direction | Priority | Action | Destination | Ports |
|------|-----------|----------|--------|-------------|-------|
| Allow Google APIs | EGRESS | 1000 | Allow | `199.36.153.4/30` (`restricted.googleapis.com`) | TCP 443 |
| Deny all other egress | EGRESS | 65534 | Deny | `0.0.0.0/0` | All |
| Allow LB health checks | INGRESS | 1000 | Allow | Google health check IP ranges | TCP 8080 |
| Allow LB backend traffic | INGRESS | 1000 | Allow | Cloud Load Balancer IP ranges | TCP 8080 |
| Deny SSH | INGRESS | 1000 | Deny | `0.0.0.0/0` | TCP 22 |

All traffic to Google Cloud services (Firestore, Cloud Storage, Cloud KMS, Cloud Logging) flows over Private Google Access, staying within Google's network. The VM cannot reach any public internet endpoint.

**Compliance mapping**: SOC 2 CC6.6 (system boundary protections), CC6.7 (restricting information transfer), ISO 27001 A.8.20 (network security), A.8.22 (segregation of networks).

---

## Attestation

### Overview

Attestation allows negotiating parties to verify that the Confidential VM is running the exact published application code with hardware memory encryption active before they submit any confidential data. This is the trust anchor of the entire system.

In the previous Nitro Enclave architecture, attestation was based on PCR values (PCR0/PCR1/PCR2) signed by the Nitro Security Module (`/dev/nsm`). In the Confidential VM architecture, attestation is based on the container image digest and OIDC identity tokens from the GCE metadata service.

### Image Digest Replaces PCR Values

| Nitro Enclave | Confidential VM |
|---------------|-----------------|
| PCR0: SHA-384 hash of enclave image | Image digest: SHA-256 hash of container image manifest |
| PCR1: SHA-384 hash of Linux kernel | Secure Boot: verified kernel via signed boot chain |
| PCR2: SHA-384 hash of application code | Image digest covers all application code and dependencies |

The container image digest is a SHA-256 hash of the image manifest. It is deterministic -- the same Dockerfile and source code always produce the same digest. The digest is recorded at build time, published for independent verification, and stored in Secret Manager.

```bash
# Record image digest after push to Artifact Registry
IMAGE_DIGEST=$(gcloud artifacts docker images describe \
  "${REGION}-docker.pkg.dev/${PROJECT_ID}/accord/accord-app:${TAG}" \
  --format="value(image_summary.digest)")

echo "Image Digest: $IMAGE_DIGEST"
# Example: sha256:a1b2c3d4e5f6...
```

### GCE Metadata Service OIDC Tokens

The Confidential VM requests an OIDC identity token from the GCE metadata service:

```bash
curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=accord&format=full"
```

The returned JWT is signed by Google (`iss: https://accounts.google.com`) and contains attestation claims:

| Claim | Description | Example Value |
|-------|-------------|---------------|
| `google.compute_engine.instance_id` | Unique VM identifier | `1234567890123456789` |
| `google.compute_engine.instance_confidentiality` | SEV-SNP status | `SEV_SNP` |
| `google.compute_engine.project_id` | GCP project | `accord-prod` |
| `google.compute_engine.zone` | VM zone | `us-central1-a` |
| `sub` | Service account unique ID | `1234567890` |
| `iss` | Token issuer (Google) | `https://accounts.google.com` |

Additionally, the Shielded VM status is queryable via the GCE metadata service:

```bash
# Confidential computing enabled
curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/attributes/confidential-compute-enabled"
# Returns: true
```

### Accord Attestation Endpoint

Accord's `GET /api/v1/attestation` endpoint combines all attestation signals into a single response:

```json
{
  "image_digest": "sha256:a1b2c3d4e5f6...",
  "sev_snp_enabled": true,
  "secure_boot": true,
  "integrity_monitoring": true,
  "vm_id": "1234567890123456789",
  "timestamp": 1710100800.0
}
```

### Client Verification Flow

Before submitting confidential data, each party must verify the attestation:

```
1. Party calls GET /api/v1/attestation
   |
2. Party compares image_digest against the published digest
   (from the project repository, security page, or independent build)
   |
   +-- If mismatch: ABORT. The deployed code does not match the audited code.
   |
3. Party verifies sev_snp_enabled == true
   |
   +-- If false: ABORT. VM memory is not hardware-encrypted.
   |
4. Party verifies secure_boot == true
   |
   +-- If false: ABORT. Boot chain is not verified.
   |
5. Party verifies integrity_monitoring == true
   |
   +-- If false: WARNING. Boot measurements may not be monitored.
   |
6. (Optional) Party decodes the OIDC identity token independently
   and verifies Google's signature using Google's public keys.
   |
7. If all checks pass: Party encrypts their configuration with the
   Accord Cloud KMS key and submits it to the onboarding endpoint.
```

**Compliance mapping**: SOC 2 CC8.1 (change management -- image digest changes on any code update), CC2.3 (communication with external parties -- attestation is publicly verifiable), ISO 27001 A.8.7 (malware protection via verified images).

---

## GPU Support

### Why GPU Support Matters

LLM-powered proposal generation is the core of Accord's negotiation engine. Each proposal requires a full inference pass through a 7B+ parameter model. Performance directly impacts user experience:

| Platform | Hardware | Inference Time per Proposal | Session Time (10 rounds) |
|----------|----------|----------------------------|--------------------------|
| Nitro Enclave | CPU only (2-4 vCPUs) | 60-180 seconds | 20-60 minutes |
| Confidential VM | NVIDIA L4 GPU | 2-5 seconds | 1-3 minutes |
| Confidential VM | NVIDIA H100 GPU | 0.5-2 seconds | 30-90 seconds |

**GPU support is the primary reason Accord migrated from Nitro Enclaves to Confidential VMs.** Nitro Enclaves do not support GPU passthrough -- all computation must run on the CPUs allocated to the enclave. This made real-time negotiation impractical for larger models.

### Available GPU Configurations

| GPU | Machine Type Family | Confidential VM Support | VRAM | Use Case |
|-----|--------------------|-----------------------|------|----------|
| NVIDIA L4 | G2 | Yes | 24 GB | Cost-effective inference for 7B-13B models |
| NVIDIA H100 80GB | A3 | Yes | 80 GB | High-performance inference for 13B-70B models |

### Memory Encryption and GPU

AMD SEV-SNP encrypts all system (CPU) memory. GPU memory (VRAM) is on a separate bus and is handled differently depending on the configuration:

| Component | Encryption |
|-----------|-----------|
| CPU memory (DRAM) | Encrypted by AMD SEV-SNP (per-VM key, hardware-enforced) |
| Data in transit on PCIe bus (CPU to GPU) | Encrypted by PCIe link encryption |
| GPU memory (VRAM) | Protected by NVIDIA Confidential Computing for supported configurations (H100 with CC mode) |

For the NVIDIA H100 with Confidential Computing mode enabled, GPU memory is encrypted at the hardware level, extending the TEE boundary to include GPU VRAM. For the NVIDIA L4, GPU memory is not hardware-encrypted, but the following compensating controls apply:

1. **No network exfiltration path**: VPC firewall rules restrict all egress to Google APIs only. An attacker cannot send GPU memory contents to an external endpoint.
2. **No persistent storage of GPU data**: Confidential data is loaded into GPU memory for inference and discarded immediately. The application zeroes GPU buffers after inference completes.
3. **No shell access**: SSH is disabled in production. An attacker cannot connect to the VM to inspect GPU memory.
4. **Physical access is controlled by GCP**: GPU cards are in Google's data centers, subject to GCP's physical security controls (SOC 2 certified).

### LLM Inference Inside the TEE

Accord uses `llama-cpp-python` with CUDA support for GPU-accelerated LLM inference:

```
Application (Python, inside Confidential VM)
  |
  +-- llama-cpp-python (Python bindings)
        |
        +-- llama.cpp (C++ inference engine)
              |
              +-- CUDA backend (NVIDIA GPU)
                    |
                    +-- NVIDIA L4 or H100 GPU
```

The model is loaded at application startup (either bundled in the container image or downloaded from Cloud Storage via Private Google Access). All inference occurs within the Confidential VM. Prompts, completions, and model weights exist in hardware-encrypted memory (CPU) and GPU VRAM.

**Compliance mapping**: ISO 27001 A.8.24 (use of cryptography -- hardware encryption of inference workload), SOC 2 CC6.7 (restricting information transfer -- inference results never leave the TEE).

---

## Trust Model Comparison

The following table provides a comprehensive side-by-side comparison of security controls between the previous AWS Nitro Enclave architecture and the current GCP Confidential VM architecture.

| Control Area | AWS Nitro Enclaves (Previous) | GCP Confidential VMs (Current) | Assessment |
|-------------|-------------------------------|-------------------------------|------------|
| **Memory encryption** | Nitro Hypervisor isolates enclave memory from parent and host | AMD SEV-SNP encrypts all VM memory with per-VM key in hardware | Equivalent. Both prevent cloud provider from reading memory. SEV-SNP provides formal cryptographic guarantee. |
| **Network isolation** | No network interface (hardware-enforced zero network) | Full network interface; VPC firewall restricts egress to Google APIs only | Reduced. Nitro had absolute zero-network. Confidential VM has compensating firewall controls. See [Compensating Controls](#compensating-controls). |
| **Disk isolation** | No filesystem (RAM-only) | Full disk (Cloud KMS-encrypted). Application policy: never write confidential data to disk. | Reduced. Nitro had hardware-enforced no-disk. Confidential VM relies on application-level discipline + encrypted disk. |
| **Shell access prevention** | No SSH, no console, no debug (hardware-enforced) | SSH disabled via IAM + firewall. Serial console disabled. All access logged in Cloud Audit Logs. | Reduced. Nitro had hardware-enforced no-shell. Confidential VM relies on IAM/firewall controls. |
| **Attestation mechanism** | PCR0/1/2 from `/dev/nsm` (Nitro Security Module), signed by AWS Nitro Attestation PKI | Image digest (SHA-256) + OIDC token from GCE metadata, signed by Google | Equivalent. Both provide cryptographically signed attestation. Different mechanisms, same trust level (trust in cloud provider's signing infrastructure). |
| **KMS key binding** | KMS key policy conditioned on PCR values (enclave identity) | Cloud KMS IAM conditioned on service account (VM identity) | Equivalent. Both restrict decryption to the specific TEE. |
| **GPU support** | Not available | NVIDIA L4 and H100 with confidential computing support | Advantage: Confidential VM. GPU acceleration is critical for production LLM inference. |
| **Provable deletion** | Enclave termination (volatile memory only) | Application-level zeroing + AMD SEV-SNP key destruction on VM termination | Equivalent. Both achieve irrecoverable data destruction. Confidential VM adds explicit application-level zeroing. |
| **Cloud provider trust** | Trust AWS for Nitro Hypervisor isolation and attestation PKI | Trust Google for GCE metadata service; trust AMD for SEV-SNP silicon | Comparable. Nitro trusts AWS proprietary hardware. Confidential VM trusts AMD open-specification silicon + Google metadata. |
| **Operational complexity** | High (parent/enclave split, vsock relay, message padding, EIF builds, PCR management) | Low (single unified application, standard networking, standard container builds) | Advantage: Confidential VM. Simpler architecture reduces operational risk and attack surface from misconfigurations. |
| **Insider threat protection** | Very high (no shell, no network, no debug -- even AWS cannot inspect enclave contents) | High (memory encrypted, SSH disabled, all access logged). Google infrastructure team could theoretically modify firewall rules, but not read encrypted memory. | Slightly reduced. See [Compensating Controls](#compensating-controls). |
| **Side-channel resistance** | Nitro Hypervisor isolation. No shared memory with host. | AMD SEV-SNP encryption. No shared memory with hypervisor. Per-VM keys prevent co-tenant side channels. | Equivalent for memory-based side channels. |
| **Audit trail** | CloudTrail for KMS. Custom vsock-forwarded application logs. | Cloud Audit Logs (automatic), VPC Flow Logs, Cloud Logging, application audit logs in Firestore. | Advantage: Confidential VM. Richer, automatic audit logging. |

---

## Compensating Controls

The most significant security difference between Nitro Enclaves and Confidential VMs is that Nitro Enclaves had hardware-enforced zero network, zero disk, and zero shell -- absolute guarantees that no data could leave the enclave except through the vsock channel. Confidential VMs have a network interface, disk, and (in principle) shell access. This section documents the compensating controls that mitigate this difference.

### Control 1: Network Egress Restriction

**Risk**: The Confidential VM has a network interface. A vulnerability or misconfiguration could allow confidential data to be sent to an external endpoint.

**Mitigation**:

| Layer | Control | Enforcement |
|-------|---------|-------------|
| VPC Firewall | Deny all egress except `restricted.googleapis.com` (199.36.153.4/30) on TCP 443 | Terraform-managed, priority 65534 deny-all + priority 1000 allow Google APIs |
| Private Google Access | All Google API traffic stays within Google's network | Enabled on the private subnet via Terraform |
| No public IP | The VM has no external IP address | Instance template configuration (Terraform) |
| Cloud NAT | Outbound internet only for initial container image pull (if needed) | Cloud NAT configured per Terraform; VM does not route through NAT for normal operations |
| DNS | Private DNS zones resolve `*.googleapis.com` to `restricted.googleapis.com` VIP | Terraform-managed DNS configuration |

**Residual risk**: An attacker who compromises the VM application and the GCP project's IAM (to modify firewall rules) could open egress. This requires a multi-layered compromise. Cloud Audit Logs record all firewall rule changes, and alerting policies trigger on unexpected modifications.

**Comparison to Nitro**: Nitro Enclaves had zero network -- no interface existed. The Confidential VM compensating control is not equivalent to zero network, but it reduces the attack surface to Google API endpoints only, which are authenticated and logged.

### Control 2: No Disk Persistence of Confidential Data

**Risk**: The Confidential VM has disk access. Confidential data could be accidentally or maliciously written to the boot disk, surviving VM termination.

**Mitigation**:

| Layer | Control | Enforcement |
|-------|---------|-------------|
| Application policy | Confidential data (party configs, session keys, negotiation logs) is never written to disk. All sensitive data exists only in RAM. | Code review, application architecture (`session.py`, `session_keys.py`) |
| Boot disk encryption | Boot disk is encrypted with a Cloud KMS key | Instance template configuration (Terraform) |
| Ephemeral disks | No persistent disks attached beyond the boot disk | Instance template configuration (Terraform) |
| AMD SEV-SNP | Even if data were written to disk, the AMD SEV-SNP key is destroyed on VM termination, and disk encryption keys are separate (Cloud KMS-managed) | Hardware + Terraform configuration |

**Residual risk**: A code defect could inadvertently write confidential data to disk (e.g., via debug logging, crash dumps). Mitigated by code review, no debug logging of sensitive fields, and boot disk encryption via Cloud KMS.

**Comparison to Nitro**: Nitro Enclaves had no filesystem. The Confidential VM compensating control relies on application discipline plus encrypted disk. The hardware-encrypted disk ensures that even if data is written, it is encrypted at rest.

### Control 3: SSH and Shell Access Prevention

**Risk**: The Confidential VM runs a standard OS and could theoretically accept SSH connections, allowing an attacker to inspect memory or exfiltrate data.

**Mitigation**:

| Layer | Control | Enforcement |
|-------|---------|-------------|
| VPC Firewall | Deny all ingress on TCP 22 from all sources | Terraform-managed firewall rule (priority 1000) |
| IAM | OS Login requires IAM authorization (`roles/compute.osLogin`). Not granted in production. | Terraform IAM configuration |
| Serial console | Disabled in production. If enabled temporarily for debugging, access is logged in Cloud Audit Logs. | Instance template metadata (`serial-port-enable: false`) |
| Cloud Audit Logs | All SSH attempts, serial console access, and IAM changes are automatically recorded | GCP-managed (Admin Activity logs, 400-day retention) |
| Alerting | Alert on any SSH connection attempt or firewall rule change | Cloud Monitoring alerting policy (Terraform) |

**Residual risk**: An attacker with GCP project Owner role could modify firewall rules and IAM to enable SSH. This requires account compromise at the highest privilege level. Cloud Audit Logs record the changes, and alerts fire immediately.

**Comparison to Nitro**: Nitro Enclaves had no shell at all -- the isolation was hardware-enforced. The Confidential VM compensating control relies on IAM and firewall rules, which are software-defined. This is a weaker guarantee, but combined with Cloud Audit Logs and alerting, provides defense-in-depth.

### Control 4: Attestation Mechanism

**Risk**: Nitro Enclaves had the Nitro Security Module (`/dev/nsm`) providing hardware-signed attestation documents with PCR measurements. Confidential VMs use a different mechanism.

**Mitigation**:

| Nitro Mechanism | Confidential VM Equivalent | Trust Root |
|----------------|---------------------------|------------|
| PCR0 (enclave image hash) | Container image digest (SHA-256) | Published digest in version control + Secret Manager |
| PCR1 (Linux kernel hash) | Secure Boot (verified boot chain) | Google-managed Shielded VM firmware |
| PCR2 (application hash) | Container image digest (covers all application code) | Published digest |
| `/dev/nsm` signed attestation document | OIDC identity token from GCE metadata, signed by Google | Google's public keys (JWK) |
| AWS Nitro Attestation PKI | Google's OIDC token signing infrastructure | Google's certificate chain |

**Residual risk**: The GCE metadata service is operated by Google. An attacker who compromises Google's metadata service could forge attestation claims. This is comparable to the risk of compromising AWS's Nitro Attestation PKI.

### Summary of Compensating Control Effectiveness

| Nitro Property | Compensating Control | Effectiveness Rating | Justification |
|---------------|---------------------|---------------------|---------------|
| Zero network | VPC firewall egress restriction | High | Egress limited to Google APIs only. No public internet path. Multi-layer compromise required to circumvent. |
| Zero disk | Application policy + Cloud KMS disk encryption | High | Code discipline enforced by review. Boot disk encrypted. Data irrecoverable after VM termination. |
| Zero shell | IAM + firewall + audit logging + alerting | High | No SSH in production. All access attempts logged and alerted. Requires IAM compromise to enable. |
| Hardware attestation (NSM) | Image digest + OIDC tokens + Shielded VM | High | Equivalent trust level. Different mechanism, same verification outcome. |

---

## Operational Considerations

### VM Lifecycle

#### Instance Creation

Confidential VMs are created via a Managed Instance Group (MIG) from an instance template:

```bash
# Verify instance template has Confidential VM enabled
gcloud compute instance-templates describe accord-prod-template \
  --format="yaml(properties.confidentialInstanceConfig,properties.shieldedInstanceConfig,properties.guestAccelerators)"
```

Expected:
```yaml
properties:
  confidentialInstanceConfig:
    enableConfidentialCompute: true
  shieldedInstanceConfig:
    enableSecureBoot: true
    enableVtpm: true
    enableIntegrityMonitoring: true
  guestAccelerators:
  - acceleratorCount: 1
    acceleratorType: .../nvidia-l4
```

The MIG ensures:
- Automatic instance recovery (autohealing) if health checks fail
- Rolling updates for zero-downtime deployments
- Consistent configuration via instance template

#### Instance Termination and Data Destruction

When a Confidential VM terminates (gracefully or due to crash):

1. The AMD Secure Processor destroys the per-VM encryption key.
2. All VM memory pages become cryptographically irrecoverable ciphertext.
3. Any active negotiation sessions are lost (this is by design -- data exists only in volatile, encrypted memory).
4. The MIG replaces the terminated instance automatically.

**Warning**: Stopping or terminating a Confidential VM is an irreversible data destruction event. All in-memory session data is lost. Always drain active sessions via the API before planned maintenance.

### Image Updates and Deployment

When the application code changes, the following procedure applies:

1. **Build** the new container image and push to Artifact Registry.
2. **Record** the new image digest (SHA-256).
3. **Publish** the new digest (version control, Secret Manager, security page).
4. **Update** the Terraform configuration with the new image reference.
5. **Apply** the Terraform change. The MIG performs a rolling update.
6. **Verify** the new instance is running: health check, attestation endpoint, SEV-SNP status.
7. **Notify** parties that the image digest has changed. Parties should re-verify attestation before submitting data.

The image digest changes with every code, dependency, or model update. This is intentional -- it ensures that parties always know exactly what code is running and can detect any change.

```bash
# Post-update verification
curl https://api.accord.example.com/api/v1/attestation | python3 -m json.tool
# Verify image_digest matches the newly published value
# Verify sev_snp_enabled == true
# Verify secure_boot == true
```

### Attestation Verification Procedures

#### For Accord Operators

After every deployment, verify:

```bash
# 1. Confirm Confidential VM is running with SEV-SNP
INSTANCE_NAME=$(gcloud compute instance-groups managed list-instances \
  accord-prod-mig --zone=us-central1-a --format='value(instance)' --limit=1)

gcloud compute instances describe "$INSTANCE_NAME" \
  --zone=us-central1-a \
  --format="yaml(confidentialInstanceConfig,shieldedInstanceConfig)"
# Expect: enableConfidentialCompute: true, enableSecureBoot: true

# 2. Confirm application attestation endpoint returns correct data
curl https://api.accord.example.com/api/v1/attestation
# Expect: image_digest matches published value, sev_snp_enabled: true

# 3. Verify Shielded VM integrity has not been violated
gcloud compute instances get-shielded-identity "$INSTANCE_NAME" \
  --zone=us-central1-a
```

#### For Negotiating Parties

Before submitting confidential data, each party should:

1. Call `GET /api/v1/attestation` and record the response.
2. Compare `image_digest` against the published value (from the project repository, security page, or their own independent build from the open-source code).
3. Confirm `sev_snp_enabled` is `true`.
4. Confirm `secure_boot` is `true`.
5. Optionally, verify the OIDC identity token signature against Google's public keys.

If any check fails, the party should not submit data.

### Monitoring and Alerting

The following metrics are critical for maintaining the security posture of the Confidential VM:

| Metric | Source | Alert Condition | Severity |
|--------|--------|-----------------|----------|
| VM Integrity Monitoring failure | Shielded VM / Cloud Monitoring | Any validation failure | Critical (potential tampering) |
| Cloud KMS decrypt failure | Cloud Audit Logs | Any unauthorized caller | Critical (potential unauthorized access) |
| Firewall rule change | Cloud Audit Logs (Admin Activity) | Any modification to egress rules | Critical (potential egress opening) |
| SSH connection attempt | VPC Flow Logs / Cloud Audit Logs | Any attempt on port 22 | High (SSH should be blocked) |
| API error rate (5xx) | Cloud Load Balancer metrics | > 1% over 5 minutes | High |
| Attestation endpoint failure | Application logs / uptime check | Any 5xx response | High (attestation unavailable) |
| MIG instance replacement | Cloud Monitoring | Any occurrence | Medium (may indicate crash) |
| GPU utilization | Cloud Monitoring (GPU metrics) | < 10% or > 95% | Medium (underutilized or overloaded) |

### Key Rotation

| Key | Rotation Schedule | Mechanism |
|-----|-------------------|-----------|
| Cloud KMS Accord key | Automatic (annual) | Google-managed rotation. Previous key versions remain available for decryption. |
| AMD SEV-SNP per-VM key | Every VM lifecycle (creation to termination) | Hardware-managed. New key on every VM launch. |
| AES-256-GCM session keys | Every negotiation session | Application-managed. New key per session, destroyed on session end. |

### Compliance Audit Evidence

For SOC 2 Type II and ISO 27001 audits, the following evidence artifacts are produced by the Confidential VM architecture:

| Evidence | Location | Retention | Relevant Control |
|----------|----------|-----------|-----------------|
| Confidential VM configuration (SEV-SNP enabled) | Terraform state, `gcloud compute instances describe` output | Duration of deployment | SOC 2 CC6.4, ISO 27001 A.8.24 |
| Container image digest history | Artifact Registry, Secret Manager, version control | Indefinite (version history) | SOC 2 CC8.1, ISO 27001 A.8.7 |
| Cloud KMS decrypt audit logs | Cloud Audit Logs (Data Access) | Configurable (default 30 days, recommended 365 days) | SOC 2 CC6.1, ISO 27001 A.5.15 |
| Firewall rule configuration and change history | Terraform state, Cloud Audit Logs (Admin Activity) | 400 days (Admin Activity, GCP-managed) | SOC 2 CC6.6, ISO 27001 A.8.20 |
| Shielded VM integrity status | Cloud Monitoring metrics | Cloud Monitoring retention (configurable) | SOC 2 CC7.1, ISO 27001 A.8.16 |
| Per-request application audit logs | Firestore `audit_log` collection | Indefinite (no TTL) | SOC 2 CC4.1, ISO 27001 A.8.15 |
| VPC Flow Logs | Cloud Logging | 365 days | SOC 2 CC7.1, ISO 27001 A.8.20 |

---

## References

- [AMD SEV-SNP Technical Overview](https://www.amd.com/en/developer/sev.html)
- [AMD SEV-SNP ABI Specification](https://www.amd.com/system/files/TechDocs/56860.pdf)
- [GCP Confidential VM Documentation](https://cloud.google.com/confidential-computing/confidential-vm/docs)
- [GCP Confidential VMs with GPU](https://cloud.google.com/confidential-computing/confidential-vm/docs/confidential-vm-with-gpus)
- [Shielded VM Documentation](https://cloud.google.com/compute/shielded-vm/docs)
- [GCE Instance Identity Tokens](https://cloud.google.com/compute/docs/instances/verifying-instance-identity)
- [Private Google Access](https://cloud.google.com/vpc/docs/private-google-access)
- [Cloud KMS Documentation](https://cloud.google.com/kms/docs)
- [NDAI Framework (arXiv:2502.07924)](https://arxiv.org/abs/2502.07924)
- [Conditional Recall (arXiv:2510.21904)](https://arxiv.org/abs/2510.21904)
