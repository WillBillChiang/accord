# Accord User Guide

## What Is Accord?

Accord is a confidential AI negotiation platform. It allows two parties -- a seller and a buyer -- to negotiate through AI agents without revealing their private constraints (budget limits, walk-away prices, strategic priorities) to each other or to the platform operator.

Your confidential data is encrypted on your device, sent to a hardware-secured Confidential VM (a GCP Confidential Virtual Machine with AMD SEV-SNP memory encryption), where AI agents negotiate on behalf of both parties. When the negotiation ends, all confidential data is provably destroyed. Neither party, nor anyone at Accord, can access the other party's private information.

---

## Getting Started

### Creating an Account

1. Navigate to the Accord web application (e.g., `https://app.accord.example.com`).
2. Click **Sign Up**.
3. Enter your email address and choose a password.
   - Password requirements: at least 12 characters, including uppercase, lowercase, numbers, and symbols.
4. Check your email for a verification link and click it to verify your account.
5. Set up Multi-Factor Authentication (MFA):
   - Open an authenticator app (e.g., Google Authenticator, Authy, 1Password).
   - Scan the QR code displayed on screen.
   - Enter the 6-digit code from your authenticator app to complete setup.

MFA is required for all accounts. This protects your account even if your password is compromised.

### Signing In

1. Navigate to the Accord web application.
2. Click **Sign In**.
3. Enter your email address and password.
4. Enter the 6-digit code from your authenticator app.
5. You will be redirected to the dashboard.

Your session lasts 1 hour. After that, you will be prompted to sign in again. The application handles token refresh automatically when possible.

---

## Creating a Negotiation Session

### Step 1: Start a New Session

1. From the dashboard, click **New Session**.
2. Fill in the session details:

| Field | Description | Required |
|-------|-------------|----------|
| **Description** | A human-readable name for the session (e.g., "Series A Negotiation with Acme Corp") | No |
| **Use Case** | The type of negotiation. Options: M&A, IP Licensing, VC Funding, NDA Replacement | No |
| **Maximum Duration** | How long the session can run before it times out (default: 1 hour) | No |

3. Click **Create Session**.

The session is now in the **Awaiting Parties** state. Both the seller and buyer must onboard before the negotiation can begin.

### Step 2: Share the Session

After creating a session, share the **Session ID** with the counterparty. Both parties need the Session ID to onboard to the same session.

You can also share a direct link to the session page: `https://app.accord.example.com/sessions/{session_id}`.

---

## Configuring Your Agent

Before onboarding to a session, you configure the AI agent that will negotiate on your behalf. This is the most important step -- your agent's behavior is determined entirely by the configuration you provide.

### Role

Select your role in the negotiation:
- **Seller**: You are selling something (an asset, a license, equity, etc.). Your agent will try to maximize the price.
- **Buyer**: You are buying something. Your agent will try to minimize the price.

### Financial Constraints

| Field | Description | Example |
|-------|-------------|---------|
| **Budget Cap** | Seller: your minimum acceptable price. Buyer: your maximum willingness to pay. The agent will never go beyond this limit. | Seller: $3,000,000 (won't sell below this). Buyer: $5,000,000 (won't pay above this). |
| **Reservation Price** | Your walk-away threshold. If the counterparty's offer meets or beats this price, your agent will accept. | Seller: $3,500,000 (will accept any offer at or above this). Buyer: $4,500,000 (will accept any offer at or below this). |

**Important distinctions:**
- **Budget Cap** is a hard floor/ceiling. Your agent physically cannot propose or accept a price beyond it.
- **Reservation Price** is your acceptance threshold. Offers meeting this price are automatically accepted.
- For sellers: budget_cap <= reservation_price (you will accept above your minimum).
- For buyers: budget_cap >= reservation_price (you will accept below your maximum).

### Negotiation Parameters

| Field | Description | Default |
|-------|-------------|---------|
| **Maximum Rounds** | How many rounds of back-and-forth your agent will participate in before stopping | 10 |
| **Maximum Concession Per Round** | The most your agent can concede in a single round (as a percentage of the previous offer). Prevents your agent from caving too quickly. | 15% |

### Disclosure Policy

For each data field you provide, you choose a disclosure tier:

| Tier | Icon | What It Means |
|------|------|---------------|
| **Must Disclose** | Always shared | This field will be included in every proposal your agent sends. Use this for information you want the counterparty to know (e.g., public company revenue). |
| **May Disclose** | Agent decides | Your AI agent can strategically choose whether to share this field during negotiation. The agent will share it if it believes disclosure would improve the deal outcome. |
| **Never Disclose** | Hard block | This field will NEVER leave the secure environment, no matter what. The system enforces this at a code level -- even if the AI tried to disclose it, the system would block it. Use this for your most sensitive information (e.g., board approval limits, competing offers). |

### Strategy Notes

Provide free-text guidance to your AI agent. This is like briefing a human negotiator. Examples:

- "Prefer milestone-based payment structure over lump sum."
- "We have time pressure -- prioritize speed over price optimization."
- "Emphasize our strong IP portfolio as leverage."
- "Be willing to concede on timeline if we get better price terms."

### Priority Issues

List the issues in order of importance to you. The agent will focus on these during negotiation. Examples:
- Price
- Payment terms
- Transition timeline
- Key employee retention
- Non-compete scope

### Acceptable Deal Structures

Specify which deal structures you would consider. Examples:
- Asset purchase
- Stock purchase
- Exclusive license
- Convertible note

### Confidential Data

Add any private data fields your agent may use during negotiation. These fields are encrypted on your device before being sent to the server. Only the Confidential VM can decrypt them.

Examples:
- Internal valuation model results
- Number of competing offers
- Board approval limit
- Revenue projections

---

## Verifying Attestation

Before submitting your confidential data, you should verify that the Confidential VM is running the exact published code with hardware memory encryption active. This is the key trust mechanism.

### What Is Attestation?

Attestation is a verification mechanism that proves the Confidential VM is running specific, unmodified code with the correct security configuration. The proof consists of:

| Value | What It Proves |
|-------|----------------|
| **Image Digest** | The exact container image (all code and dependencies) running in the VM. This is a SHA-256 hash that changes if any file in the application changes. |
| **SEV-SNP Enabled** | Confirms that AMD SEV-SNP hardware memory encryption is active, meaning all VM memory is encrypted and the cloud provider cannot read it. |
| **Secure Boot** | Confirms that the VM booted with verified firmware, preventing boot-level tampering. |

### How to Verify

1. On the session page, click **Verify Attestation**.
2. The application fetches the live attestation information from the running Confidential VM.
3. Compare these values against the **published values**:
   - Check the Accord project repository for the latest published image digest.
   - Check the Accord security page.
   - If you are technically inclined, you can build the container image yourself from the open-source code and verify the image digest matches.
4. Confirm that SEV-SNP is shown as **Enabled** (green checkmark).
5. If the image digest matches and SEV-SNP is active, the VM is running the exact published code with hardware memory encryption. It is safe to submit your data.
6. If the image digest does not match or SEV-SNP is not enabled, **do not submit your data**. Contact Accord support.

### Why This Matters

The image digest is a cryptographic hash of the entire application container. If anyone modified the code -- to steal data, change the protocol, or add a backdoor -- the digest would change, and verification would fail. The SEV-SNP status confirms that all VM memory is hardware-encrypted, meaning even Google (the cloud provider) cannot read the data in the VM.

---

## Onboarding to a Session

Once you have configured your agent and verified the attestation:

1. On the session page, click **Onboard**.
2. Select your role (seller or buyer).
3. Fill in your agent configuration (or load a saved configuration).
4. Review your disclosure policy one final time.
5. Click **Submit Configuration**.

What happens behind the scenes:
1. Your configuration is encrypted on your device using the Accord Cloud KMS key.
2. The encrypted blob is sent to the server.
3. The server (running inside the Confidential VM) decrypts your configuration using its Cloud KMS access.
4. Your configuration is stored only in the VM's hardware-encrypted memory.
5. Your agent is ready.

The session status changes to **Onboarding** after the first party joins, and to **Ready** after both parties have onboarded.

---

## Monitoring Negotiation Progress

### Starting the Negotiation

Once both parties are onboarded, either party can click **Start Negotiation** on the session page.

The negotiation proceeds through these phases:

1. **ZOPA Check**: The system checks whether an agreement is even possible (seller's minimum <= buyer's maximum). This check reveals only a yes/no result -- neither party learns the other's actual numbers.

2. **SAO Protocol**: If ZOPA exists, the AI agents begin alternating offers:
   - The seller's agent makes the opening offer.
   - The buyer's agent evaluates: accept, counter, or reject.
   - Roles alternate each round.
   - This continues until agreement, rejection, or round exhaustion.

3. **Nash Bargaining Fallback**: If all rounds are exhausted without agreement, the system computes a fair price using the Nash Bargaining Solution (a game-theory-based formula using both parties' private prices).

### Real-Time Updates

During negotiation, the session page displays:

| Information | Description |
|-------------|-------------|
| **Current Round** | Which round of negotiation is in progress |
| **Status** | Current phase (ZOPA check, negotiating, etc.) |
| **Round Log** | Redacted log showing each round's action (proposal, counter, accept, reject) without revealing actual prices or terms |
| **Progress Indicator** | Visual progress toward maximum rounds |

The page updates in real-time via WebSocket. You do not need to refresh.

### What You Can See During Negotiation

For privacy, you can see:
- Round numbers and timestamps
- Action types (proposal, counter, accept, reject)
- Which party took each action
- Whether a price was offered (yes/no, not the amount)
- Whether terms were included (yes/no, not the content)

You **cannot** see:
- The actual prices proposed
- The specific terms discussed
- The counterparty's rationale
- The counterparty's private data

This information exists only inside the Confidential VM and is destroyed when the session ends.

---

## Understanding Results

When the negotiation completes, the session page displays the outcome.

### Deal Reached

If the agents reached an agreement:

| Field | Description |
|-------|-------------|
| **Outcome** | "Deal Reached" |
| **Final Price** | The agreed-upon price |
| **Final Terms** | The agreed-upon deal terms |
| **Rounds Completed** | How many rounds were needed |
| **Method** | Whether the deal was reached through SAO (direct negotiation) or Nash Bargaining (fallback) |

Both parties see the same final price and terms. These are the terms your agents agreed to based on the constraints you provided.

### No Deal

If the agents could not reach an agreement, the outcome indicates why:

| Outcome | Meaning |
|---------|---------|
| **No ZOPA** | The seller's minimum price is higher than the buyer's maximum willingness to pay. No agreement was possible at any price. |
| **No Agreement** | ZOPA existed, but the agents could not converge on a price within the allowed rounds, and the Nash Bargaining Solution was also unacceptable to one or both parties. |
| **Rejected** | One party's agent explicitly rejected the negotiation. |
| **Timeout** | The session exceeded its maximum duration. |

### After the Negotiation

Regardless of outcome, when the session ends:
1. All confidential data inside the Confidential VM is cryptographically destroyed.
2. Session encryption keys are securely zeroed.
3. Neither party can recover the other's private configuration.
4. The only information that persists is: the outcome, final terms (if deal), round count, and the redacted audit log.
5. When the VM eventually terminates, the AMD SEV-SNP memory encryption key is destroyed, rendering all VM memory physically irrecoverable.

---

## Viewing Audit Logs

Accord maintains a complete audit trail for compliance and dispute resolution.

### Session Audit Log

1. Navigate to the session page.
2. Click **Audit Log**.
3. View entries showing:
   - When each party onboarded
   - When the negotiation started
   - Round-by-round actions (redacted)
   - When the negotiation completed
   - The outcome

### Account Audit Log

1. From the dashboard, click **Audit Logs** in the navigation.
2. View all API actions associated with your account:
   - Session creation and deletion
   - Onboarding events
   - Negotiation starts
   - Status queries
   - Attestation verifications

### Admin Audit Log

If you are an admin, you can view audit logs for all users. Use the filter controls to search by user, session, or time range.

---

## Frequently Asked Questions

### Can Accord or the platform operator see my confidential data?

No. Your data is encrypted on your device before it is sent. The decryption key access is restricted to the Confidential VM's service account. Additionally, the Confidential VM uses AMD SEV-SNP hardware memory encryption, which means even Google (the cloud provider) cannot read the VM's memory contents. Your data exists only in hardware-encrypted memory that no one outside the VM can access.

### What happens to my data after the negotiation?

It is provably destroyed. The application cryptographically zeros all data in memory, destroys the session encryption keys, and clears all logs. The data never touches disk. When the VM terminates, AMD SEV-SNP destroys the memory encryption key, making all VM memory physically irrecoverable.

### How do I know the Confidential VM is running the code you published?

You verify the attestation. The attestation contains the container image digest (a SHA-256 hash of the application) and the SEV-SNP status. You compare the image digest against the published value. If they match and SEV-SNP is active, the VM is running exactly what was published with hardware memory encryption. Any code modification would change the digest.

### What if the negotiation fails or the system crashes?

If the system crashes during a negotiation, all data in the Confidential VM is immediately destroyed (AMD SEV-SNP destroys the memory encryption key when the VM terminates). You will need to create a new session and start over. The Firestore record will show the last known status.

### Can I reuse a session for multiple negotiations?

No. Each session is single-use. When it terminates (for any reason), all data is destroyed and the session cannot be restarted. Create a new session for each negotiation.

### Can my agent exceed my budget cap?

No. The budget cap is enforced by the system at the code level, not by instructing the AI. Even if the AI agent attempted to propose a price beyond your budget cap, the system would automatically clamp or reject it before it is sent. This is a hard guarantee.

### What if the AI agent makes a bad deal?

The agent will never accept a deal worse than your reservation price. If the counterparty's offer meets or exceeds your reservation price, the agent will accept it. Set your reservation price carefully -- it defines the boundary of what you consider an acceptable deal.

### Can I customize my agent's negotiation strategy?

Yes. Use the **Strategy Notes** field to provide guidance (like briefing a human negotiator). Use **Priority Issues** to tell the agent what matters most. Use **Maximum Concession Per Round** to control how quickly the agent makes concessions. The more specific your guidance, the better your agent will negotiate.

### What does "May Disclose" mean in practice?

When a field is set to "May Disclose," the AI agent decides during negotiation whether sharing it would be strategically beneficial. For example, if you mark your growth rate as "May Disclose," the agent might share it early to build credibility, or withhold it if the negotiation is going well without it.

### Can I see what the counterparty's agent disclosed?

You can see the final agreed terms if a deal is reached. During the negotiation, you can see that proposals were made (redacted log), but not the specific content. After the session ends, all proposal details are destroyed.

### How is this different from the previous system?

The previous system used AWS Nitro Enclaves, which had zero network access and zero disk access. The current system uses GCP Confidential VMs, which have network and disk access but encrypt all VM memory at the hardware level (AMD SEV-SNP). To compensate for the network access, VPC firewall rules restrict the VM to communicate only with Google Cloud services -- it cannot reach the public internet. The confidential data never touches disk; it exists only in hardware-encrypted RAM.

### Is this legally binding?

Accord facilitates negotiation and produces agreed terms, but the legal enforceability of those terms depends on your jurisdiction and the context of the negotiation. We recommend having legal counsel review any agreement reached through Accord before executing formal contracts.

### How long does a typical negotiation take?

This depends on the use case and configuration. With 10 rounds and GPU-accelerated inference, a typical negotiation completes in under 1 minute. More complex negotiations with more rounds may take longer. The maximum session duration (default: 1 hour) ensures sessions do not run indefinitely.

### I forgot my password. How do I reset it?

1. Click **Forgot Password** on the sign-in page.
2. Enter your email address.
3. Check your email for a reset link.
4. Click the link and set a new password.
5. You will need your authenticator app (MFA) to complete sign-in after resetting.

### Who do I contact for support?

For technical issues, contact support at the email provided on the application's help page. For security concerns (e.g., attestation verification failure), contact the security team immediately.
