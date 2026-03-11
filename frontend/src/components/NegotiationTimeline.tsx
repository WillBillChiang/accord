'use client';

import { ProposalCard } from './ProposalCard';
import type { Proposal } from '@/types/negotiation';

interface NegotiationTimelineProps {
  proposals: Proposal[];
  currentUserPartyId?: string;
}

export function NegotiationTimeline({
  proposals,
  currentUserPartyId,
}: NegotiationTimelineProps) {
  if (proposals.length === 0) {
    return (
      <div className="text-center py-10 text-gray-500">
        No proposals yet. Negotiation has not started.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {proposals.map((proposal) => (
        <ProposalCard
          key={proposal.proposal_id}
          proposal={proposal}
          isOwnProposal={proposal.from_party === currentUserPartyId}
        />
      ))}
    </div>
  );
}
