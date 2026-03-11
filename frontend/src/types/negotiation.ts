export enum DisclosureTier {
  MUST_DISCLOSE = 'must_disclose',
  MAY_DISCLOSE = 'may_disclose',
  NEVER_DISCLOSE = 'never_disclose',
}

export enum NegotiationRole {
  SELLER = 'seller',
  BUYER = 'buyer',
}

export enum SessionStatus {
  AWAITING_PARTIES = 'awaiting_parties',
  ONBOARDING = 'onboarding',
  ZOPA_CHECK = 'zopa_check',
  NEGOTIATING = 'negotiating',
  DEAL_REACHED = 'deal_reached',
  NO_DEAL = 'no_deal',
  EXPIRED = 'expired',
  ERROR = 'error',
}

export enum ProposalAction {
  ACCEPT = 'accept',
  COUNTER = 'counter',
  REJECT = 'reject',
}

export interface PartyConfig {
  party_id?: string;
  role: NegotiationRole;
  budget_cap: number;
  reservation_price: number;
  max_rounds: number;
  max_concession_per_round: number;
  disclosure_fields: Record<string, DisclosureTier>;
  strategy_notes: string;
  priority_issues: string[];
  acceptable_deal_structures: string[];
}

export interface Proposal {
  proposal_id: string;
  round_number: number;
  from_party: string;
  price: number;
  terms: Record<string, unknown>;
  disclosed_fields: Record<string, string>;
  rationale: string;
  timestamp: number;
}

export interface ProposalResponse {
  response_id: string;
  action: ProposalAction;
  counter_proposal?: Proposal;
  rationale: string;
  timestamp: number;
}

export interface NegotiationOutcome {
  session_id: string;
  outcome: string;
  reason: string;
  final_terms?: Record<string, unknown>;
  final_price?: number;
  rounds_completed: number;
  started_at: number;
  completed_at: number;
}

export interface Session {
  sessionId: string;
  status: SessionStatus;
  createdAt: number;
  createdBy: string;
  description: string;
  useCase: string;
  sellerOnboarded: boolean;
  buyerOnboarded: boolean;
  finalTerms?: Record<string, unknown>;
  finalPrice?: number;
  roundsCompleted?: number;
}

export interface AttestationDocument {
  pcr0: string;
  pcr1: string;
  pcr2: string;
  timestamp: number;
  nonce?: string;
}

export interface AuditLogEntry {
  auditId: string;
  timestamp: number;
  sessionId: string;
  action: string;
  userId: string;
  outcome?: string;
}

export interface CreateSessionRequest {
  max_duration_sec?: number;
  description?: string;
  use_case?: string;
}

export interface OnboardPartyRequest {
  role: NegotiationRole;
  config: PartyConfig;
}
