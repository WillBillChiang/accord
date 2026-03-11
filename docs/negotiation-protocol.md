# Accord Negotiation Protocol Specification

## Overview

Accord implements a multi-phase negotiation protocol that combines the Stacked Alternating Offers (SAO) mechanism with Nash Bargaining Solution as a fallback. The protocol runs entirely inside a GCP Confidential VM (AMD SEV-SNP), ensuring that neither party's confidential constraints are exposed to the other party, the platform operator, or any third party.

The protocol is grounded in the NDAI framework (arXiv:2502.07924) and follows a key design principle: **hard constraints are enforced in code; soft strategy is delegated to the LLM**. The Confidential VM guarantees that no AI agent can violate budget caps, disclosure boundaries, or concession limits, regardless of what the LLM generates.

## Protocol Phases

```
Phase 1          Phase 2          Phase 3         Phase 4           Phase 5
Session       Party Onboarding   ZOPA Check    SAO Negotiation   Termination
Creation      (Seller + Buyer)   (Boolean)     (Up to N rounds)  & Deletion
   |               |                |               |                |
   v               v                v               v                v
+--------+   +-----------+   +-----------+   +-------------+   +----------+
| Create |-->| Decrypt   |-->| seller_min|-->| Alternating |-->| Outcome  |
| session|   | configs   |   | <= buyer_ |   | offers with |   | + secure |
| in VM  |   | via KMS   |   | max?      |   | preflight   |   | deletion |
|        |   | (IAM)     |   |           |   | checks      |   |          |
+--------+   +-----------+   +-----+-----+   +------+------+   +----------+
                                   |                |
                              No ZOPA?         Exhausted?
                                   |                |
                              Terminate        Nash Bargaining
                              (no_deal)          Fallback
```

## Phase 1: Session Creation

A session is created with a maximum duration and use case identifier. The application allocates an ephemeral AES-256-GCM session key and initializes the session state.

**Session States:**

| State | Description |
|-------|-------------|
| `awaiting_parties` | Session created, waiting for both parties to onboard |
| `onboarding` | One party has onboarded, waiting for the second |
| `zopa_check` | Both parties onboarded, ready for ZOPA check |
| `negotiating` | SAO protocol is running |
| `deal_reached` | Agreement reached |
| `no_deal` | No agreement (no ZOPA, rejected, no agreement after Nash) |
| `expired` | Session exceeded maximum duration |
| `error` | Unrecoverable error |

## Phase 2: Party Onboarding

Each party submits their configuration encrypted with the Accord Cloud KMS key. The encryption happens client-side. Only the Confidential VM can decrypt the configuration because Cloud KMS IAM restricts the decrypt permission to the VM's service account.

### Party Configuration (`PartyConfig`)

Each party configures their AI agent with the following parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `role` | `seller` or `buyer` | The party's role in the negotiation |
| `budget_cap` | float (> 0) | Seller: minimum acceptable price. Buyer: maximum willingness to pay. |
| `reservation_price` | float (> 0) | Walk-away price (the threshold for accepting an offer) |
| `max_rounds` | int (1-50) | Maximum number of negotiation rounds this agent will participate in |
| `max_concession_per_round` | float (0.01-1.0) | Maximum percentage the agent can concede in a single round |
| `disclosure_fields` | dict | Map of field names to disclosure tiers (see below) |
| `strategy_notes` | string | Free-text strategic guidance for the LLM agent |
| `priority_issues` | list | Ordered list of priority negotiation issues |
| `acceptable_deal_structures` | list | List of acceptable deal structures |
| `confidential_data` | dict | Private data fields only accessible inside the Confidential VM |

### Disclosure Tiers

Each data field can be assigned a disclosure tier that controls whether the AI agent can reveal it to the counterparty:

| Tier | Value | Behavior |
|------|-------|----------|
| **MUST_DISCLOSE** | `must_disclose` | The agent is required to share this field. Enforced by including it in every proposal's `disclosed_fields`. |
| **MAY_DISCLOSE** | `may_disclose` | The agent may strategically choose to share or withhold this field. The LLM decides based on negotiation dynamics. |
| **NEVER_DISCLOSE** | `never_disclose` | The field is hard-blocked from ever leaving the Confidential VM. The preflight check will reject any proposal that includes a NEVER_DISCLOSE field, regardless of what the LLM generates. |

Example disclosure configuration:

```json
{
  "company_revenue": "must_disclose",
  "growth_rate": "may_disclose",
  "competing_offers": "may_disclose",
  "board_approval_limit": "never_disclose",
  "internal_valuation_model": "never_disclose"
}
```

## Phase 3: ZOPA Check

Before running the negotiation, the application computes whether a Zone of Possible Agreement exists.

**Definition:** ZOPA exists when `seller_minimum <= buyer_maximum` (i.e., `seller.budget_cap <= buyer.budget_cap`).

**Privacy guarantee:** The ZOPA check returns only a boolean result (`true`/`false`). The actual values of `seller_minimum` and `buyer_maximum` are never revealed to either party. The ZOPA range (`buyer_max - seller_min`) is computed internally for use by the Nash Bargaining fallback but never leaves the Confidential VM.

If no ZOPA exists, the session terminates immediately with outcome `no_zopa`. Neither party learns the other's actual boundary -- they only learn that no overlap exists.

## Phase 4: SAO Protocol

### Stacked Alternating Offers (SAO)

SAO is the core negotiation mechanism. It proceeds in rounds where agents alternate between proposing and evaluating.

**Protocol flow:**

```
Round 1:  Seller proposes  -->  Buyer evaluates  -->  Accept / Counter / Reject
Round 2:  Buyer proposes   -->  Seller evaluates -->  Accept / Counter / Reject
Round 3:  Seller proposes  -->  Buyer evaluates  -->  Accept / Counter / Reject
  ...
Round N:  [proposer]       -->  [evaluator]      -->  Accept / Counter / Reject
          (max rounds exhausted) --> Nash Bargaining Fallback
```

### Round Progression and Turn Order

1. The **seller** always makes the opening offer (Round 1).
2. After each counter, the roles swap: the evaluator becomes the proposer for the next round.
3. Each round consists of:
   - **Proposal generation**: The current proposer's agent generates a proposal.
   - **Preflight check**: The proposal is validated against hard constraints.
   - **Evaluation**: The current evaluator's agent evaluates the proposal.
   - **Response**: The evaluator responds with `accept`, `counter`, or `reject`.

### Proposal Schema

Each proposal contains:

| Field | Type | Description |
|-------|------|-------------|
| `proposal_id` | UUID | Unique proposal identifier |
| `round_number` | int | Current round number |
| `from_party` | string | Party ID of the proposer |
| `price` | float | Proposed price |
| `terms` | dict | Additional deal terms (structure, timeline, etc.) |
| `disclosed_fields` | dict | Fields the proposer chose to disclose |
| `rationale` | string | LLM-generated reasoning |
| `timestamp` | float | Unix timestamp |

### Response Actions

| Action | Description |
|--------|-------------|
| `accept` | The evaluator accepts the proposal. Negotiation ends with `deal_reached`. |
| `counter` | The evaluator rejects the current offer and proposes a counter. Negotiation continues. |
| `reject` | The evaluator explicitly rejects. Negotiation ends with `rejected`. |

### Acceptance Logic

The evaluator's agent accepts a proposal when the offered price meets the reservation price threshold:

- **Seller accepts** when `offered_price >= seller.reservation_price`
- **Buyer accepts** when `offered_price <= buyer.reservation_price`

### Maximum Rounds

The effective maximum rounds is `min(seller.max_rounds, buyer.max_rounds)`. When rounds are exhausted without agreement, the protocol proceeds to Nash Bargaining.

## Preflight Constraint Enforcement

Every proposal generated by the LLM passes through a preflight check before being sent. This is a pure Python function (no LLM involved) that enforces all hard constraints. This implements NDAI Theorem 1: safety constraints must be enforced computationally, not by LLM prompt.

### Constraint Checks

#### 1. Budget Cap (NDAI Theorem 1)

```
Buyer:  If proposed_price > budget_cap:
            clamp price down to budget_cap (truncate, don't reject)

Seller: If proposed_price < budget_cap:
            REJECT proposal (PreflightViolation)
```

The buyer's budget cap is enforced by clamping (silently reducing the price) rather than rejecting, per NDAI's design. The seller's minimum is enforced strictly.

#### 2. Concession Rate Limit

```
concession = |current_price - last_own_price| / last_own_price

If concession > max_concession_per_round:
    REJECT proposal (PreflightViolation)
```

This prevents the LLM from making excessively large concessions in a single round, protecting the principal from an overly accommodating agent.

#### 3. Disclosure Boundary Enforcement

```
For each field in proposal.disclosed_fields:
    If config.disclosure_fields[field] == NEVER_DISCLOSE:
        REJECT proposal (PreflightViolation)
```

Fields marked `NEVER_DISCLOSE` are hard-blocked from ever appearing in outgoing proposals. This is the computational equivalent of a confidentiality firewall.

#### 4. Round Limit

```
If proposal.round_number > config.max_rounds:
    REJECT proposal (PreflightViolation)
```

### Retry Loop

When a preflight violation occurs:

1. The violation is logged (constraint name + message).
2. The LLM is asked to regenerate the proposal (up to 3 retries).
3. If all retries fail, a **fallback proposal** is generated using a rule-based strategy that is guaranteed to satisfy all constraints.

```
generate_proposal():
    for attempt in [1, 2, 3]:
        proposal = LLM.generate()
        try:
            proposal = preflight_check(proposal, config, history)
            return proposal  # Passed all checks
        except PreflightViolation:
            continue  # Retry
    return fallback_proposal()  # Safe default
```

## Agent Decision Flow

### LLM-Powered Generation

Each agent uses a language model running locally inside the Confidential VM. With GPU support (NVIDIA H100 or L4 with confidential computing), inference is significantly faster than CPU-only execution. The LLM has no access to the public internet (VPC firewall restricts egress to Google APIs only).

**System prompt structure:**

```
Role: {seller|buyer}
Hard Constraints:
  - Budget cap: ${value}
  - Max concession: {percentage}%
  - Remaining rounds: {N}
  - Reservation price: ${value}
Strategy Guidance (from principal):
  {free-text strategy notes}
  Priority issues: {list}
  Acceptable structures: {list}
Disclosure Policy:
  - field_1: MUST disclose
  - field_2: MAY disclose
  - field_3: NEVER disclose
Output: JSON with price, terms, disclosed_fields, rationale
```

**Key design decisions:**

- The LLM sees the principal's full private context (budget, strategy, reservation price) because it runs inside the Confidential VM.
- The LLM generates natural-language rationale for each proposal, enabling sophisticated negotiation reasoning.
- Hard constraints are NOT relayed to the LLM as instructions to follow -- they are enforced computationally by the preflight check after the LLM generates output.
- The LLM's temperature is set to 0.3 for deterministic but not fully greedy generation.

### Fallback Strategy (No LLM)

When the LLM is unavailable or all retries fail, a rule-based fallback generates proposals:

**Seller fallback:**
```
start_price = budget_cap * 1.5
target = reservation_price
progress = (round - 1) / (max_rounds - 1)
price = start_price - (start_price - target) * progress * 0.5
price = max(price, budget_cap)  # Never below minimum
```

**Buyer fallback:**
```
start_price = budget_cap * 0.5
target = reservation_price
progress = (round - 1) / (max_rounds - 1)
price = start_price + (target - start_price) * progress * 0.5
price = min(price, budget_cap)  # Never above maximum
```

Both fallbacks automatically include MUST_DISCLOSE fields in disclosed_fields.

## Nash Bargaining Solution (Fallback)

When the SAO protocol exhausts all rounds without agreement, the application computes the Nash Bargaining Solution using both parties' private reservation prices. This computation is only possible inside the Confidential VM where both parties' private data is accessible.

### Mathematical Formulation

From NDAI Equations (4)-(5):

**Total deal value:**
```
omega = buyer.budget_cap  (estimated from buyer's maximum willingness to pay)
```

**Seller's outside option fraction:**
```
alpha_0 = seller.budget_cap / omega
```

This represents the seller's next-best alternative as a fraction of the total deal value.

**Equilibrium share parameter:**
```
theta = (1 + alpha_0) / 2
```

**Nash Bargaining Price:**
```
P* = theta * omega = ((1 + alpha_0) / 2) * omega
```

**Payoffs:**
```
Seller payoff = P*
Buyer payoff  = omega - P*
```

### Reservation Price Clamping

After computing the Nash price, it is clamped to respect both parties' reservation prices:

```
If P* < seller.reservation_price:
    P* = seller.reservation_price

If P* > buyer.reservation_price:
    P* = buyer.reservation_price
```

### Acceptance Check

The Nash price is accepted if both parties would agree:

```
seller_accepts = P* >= seller.reservation_price
buyer_accepts  = P* <= buyer.reservation_price

If seller_accepts AND buyer_accepts:
    outcome = deal_reached (via Nash)
Else:
    outcome = no_agreement
```

### Example Calculation

```
Seller budget_cap (minimum): $3,000,000
Buyer budget_cap (maximum):  $5,000,000
Seller reservation_price:    $3,500,000
Buyer reservation_price:     $4,500,000

omega   = $5,000,000
alpha_0 = $3,000,000 / $5,000,000 = 0.6
theta   = (1 + 0.6) / 2 = 0.8
P*      = 0.8 * $5,000,000 = $4,000,000

Seller payoff: $4,000,000 (>= $3,500,000 reservation -- accepts)
Buyer payoff:  $1,000,000 (<= $4,500,000 reservation -- accepts)

Result: Deal at $4,000,000
```

## Use Case Configurations

Accord supports multiple negotiation domains with tailored configurations.

### M&A (Mergers & Acquisitions)

```json
{
  "use_case": "ma",
  "typical_config": {
    "max_rounds": 15,
    "max_concession_per_round": 0.10,
    "priority_issues": [
      "enterprise_value",
      "payment_structure",
      "earnout_terms",
      "transition_timeline",
      "key_employee_retention"
    ],
    "acceptable_deal_structures": [
      "asset_purchase",
      "stock_purchase",
      "merger"
    ],
    "disclosure_fields": {
      "revenue": "must_disclose",
      "ebitda": "must_disclose",
      "customer_count": "may_disclose",
      "churn_rate": "may_disclose",
      "board_approval_limit": "never_disclose",
      "competing_bids": "never_disclose"
    }
  }
}
```

### IP Licensing

```json
{
  "use_case": "ip_licensing",
  "typical_config": {
    "max_rounds": 10,
    "max_concession_per_round": 0.15,
    "priority_issues": [
      "royalty_rate",
      "exclusivity",
      "territory",
      "field_of_use",
      "sublicensing_rights",
      "term_length"
    ],
    "acceptable_deal_structures": [
      "exclusive_license",
      "non_exclusive_license",
      "field_of_use_license"
    ],
    "disclosure_fields": {
      "patent_portfolio_size": "must_disclose",
      "prior_licenses": "may_disclose",
      "litigation_risk": "never_disclose"
    }
  }
}
```

### VC Funding

```json
{
  "use_case": "vc_funding",
  "typical_config": {
    "max_rounds": 8,
    "max_concession_per_round": 0.12,
    "priority_issues": [
      "pre_money_valuation",
      "investment_amount",
      "equity_percentage",
      "board_seats",
      "liquidation_preference",
      "anti_dilution"
    ],
    "acceptable_deal_structures": [
      "series_a_preferred",
      "convertible_note",
      "safe"
    ],
    "disclosure_fields": {
      "revenue_metrics": "must_disclose",
      "burn_rate": "must_disclose",
      "runway_months": "may_disclose",
      "other_term_sheets": "never_disclose",
      "minimum_valuation": "never_disclose"
    }
  }
}
```

### NDA Replacement

For cases where the negotiation itself serves as a structured alternative to traditional NDAs:

```json
{
  "use_case": "nda_replacement",
  "typical_config": {
    "max_rounds": 5,
    "max_concession_per_round": 0.20,
    "priority_issues": [
      "scope_of_information",
      "permitted_use",
      "exclusion_categories",
      "term_duration",
      "return_destroy_obligations"
    ],
    "acceptable_deal_structures": [
      "mutual_disclosure",
      "one_way_disclosure"
    ],
    "disclosure_fields": {
      "information_categories": "must_disclose",
      "intended_purpose": "must_disclose",
      "sensitive_details": "never_disclose"
    }
  }
}
```

## Protocol Guarantees

| Guarantee | Mechanism |
|-----------|-----------|
| Budget cap cannot be exceeded | Preflight enforcement (code, not prompt) |
| NEVER_DISCLOSE fields cannot leak | Preflight enforcement (hard block) |
| Concession rate is bounded | Preflight enforcement (per-round check) |
| Round limits are respected | Preflight enforcement + protocol loop |
| ZOPA check reveals only boolean | Code-level output filtering |
| Private data destroyed after session | Cryptographic zeroing + AMD SEV-SNP key destruction on VM termination |
| Nash computation uses true private values | Only possible inside Confidential VM where both configs exist in memory |
| No party can observe the other's raw input | Confidential VM isolation (AMD SEV-SNP hardware memory encryption, VPC firewall restricts egress) |
