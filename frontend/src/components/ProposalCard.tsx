import type { Proposal } from '@/types/negotiation';

interface ProposalCardProps {
  proposal: Proposal;
  isOwnProposal: boolean;
}

export function ProposalCard({ proposal, isOwnProposal }: ProposalCardProps) {
  return (
    <div
      className={`rounded-xl p-5 border ${
        isOwnProposal
          ? 'bg-blue-950/30 border-blue-800/50 ml-8'
          : 'bg-gray-900 border-gray-800 mr-8'
      }`}
    >
      <div className="flex justify-between items-start mb-3">
        <div>
          <span className="text-xs font-medium text-gray-500">
            Round {proposal.round_number}
          </span>
          <span className="text-xs text-gray-600 ml-2">
            {new Date(proposal.timestamp * 1000).toLocaleTimeString()}
          </span>
        </div>
        <span className="text-lg font-semibold text-white">
          ${proposal.price.toLocaleString()}
        </span>
      </div>
      {proposal.rationale && (
        <p className="text-sm text-gray-400 mb-3">{proposal.rationale}</p>
      )}
      {Object.keys(proposal.terms).length > 0 && (
        <div className="mt-2">
          <span className="text-xs font-medium text-gray-500">Terms:</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {Object.entries(proposal.terms).map(([key, value]) => (
              <span
                key={key}
                className="px-2 py-1 bg-gray-800 rounded text-xs text-gray-300"
              >
                {key}: {String(value)}
              </span>
            ))}
          </div>
        </div>
      )}
      {Object.keys(proposal.disclosed_fields).length > 0 && (
        <div className="mt-2">
          <span className="text-xs font-medium text-gray-500">Disclosed:</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {Object.entries(proposal.disclosed_fields).map(([key, value]) => (
              <span
                key={key}
                className="px-2 py-1 bg-green-950/50 border border-green-800/30 rounded text-xs text-green-300"
              >
                {key}: {value}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
