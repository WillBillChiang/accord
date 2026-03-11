'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { SessionStatusBadge } from '@/components/SessionStatusBadge';
import { NegotiationTimeline } from '@/components/NegotiationTimeline';
import { AuditLogViewer } from '@/components/AuditLogViewer';
import { SessionStatus } from '@/types/negotiation';

export default function NegotiationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const sessionId = params.id as string;

  const { data: session, isLoading, error } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => apiClient.getSession(sessionId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (
        status === SessionStatus.NEGOTIATING ||
        status === SessionStatus.ZOPA_CHECK ||
        status === SessionStatus.ONBOARDING
      ) {
        return 3000;
      }
      return false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () => apiClient.startNegotiation(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] });
    },
  });

  const terminateMutation = useMutation({
    mutationFn: () => apiClient.terminateSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['session', sessionId] });
      queryClient.invalidateQueries({ queryKey: ['sessions'] });
    },
  });

  if (isLoading) {
    return <div className="text-gray-400">Loading session...</div>;
  }

  if (error || !session) {
    return (
      <div className="text-center py-20">
        <p className="text-red-400 mb-4">Failed to load session</p>
        <Link href="/dashboard" className="text-blue-400 hover:underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const isTerminal = [
    SessionStatus.DEAL_REACHED,
    SessionStatus.NO_DEAL,
    SessionStatus.EXPIRED,
    SessionStatus.ERROR,
  ].includes(session.status);

  const canStart =
    session.sellerOnboarded &&
    session.buyerOnboarded &&
    session.status === SessionStatus.AWAITING_PARTIES;

  return (
    <div>
      <div className="flex items-center gap-3 mb-8">
        <Link
          href="/dashboard"
          className="text-gray-400 hover:text-white transition"
        >
          &larr; Back
        </Link>
      </div>

      {/* Session header */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h1 className="text-xl font-bold text-white">
              {session.description || session.sessionId}
            </h1>
            <p className="text-gray-500 text-sm mt-1">
              {session.useCase || 'General negotiation'} &middot; Session{' '}
              {session.sessionId.slice(0, 8)}...
            </p>
          </div>
          <SessionStatusBadge status={session.status} />
        </div>

        {/* Party status */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div
            className={`rounded-lg p-4 border ${
              session.sellerOnboarded
                ? 'bg-green-950/20 border-green-800/30'
                : 'bg-gray-800 border-gray-700'
            }`}
          >
            <p className="text-sm font-medium text-gray-300">Seller</p>
            <p
              className={`text-sm ${session.sellerOnboarded ? 'text-green-400' : 'text-gray-500'}`}
            >
              {session.sellerOnboarded ? 'Onboarded' : 'Awaiting onboarding'}
            </p>
          </div>
          <div
            className={`rounded-lg p-4 border ${
              session.buyerOnboarded
                ? 'bg-green-950/20 border-green-800/30'
                : 'bg-gray-800 border-gray-700'
            }`}
          >
            <p className="text-sm font-medium text-gray-300">Buyer</p>
            <p
              className={`text-sm ${session.buyerOnboarded ? 'text-green-400' : 'text-gray-500'}`}
            >
              {session.buyerOnboarded ? 'Onboarded' : 'Awaiting onboarding'}
            </p>
          </div>
        </div>

        {/* Summary stats */}
        {(session.roundsCompleted !== undefined ||
          session.finalPrice !== undefined) && (
          <div className="flex gap-6 text-sm">
            {session.roundsCompleted !== undefined && (
              <div>
                <span className="text-gray-500">Rounds:</span>{' '}
                <span className="text-white">{session.roundsCompleted}</span>
              </div>
            )}
            {session.finalPrice !== undefined && (
              <div>
                <span className="text-gray-500">Final Price:</span>{' '}
                <span className="text-green-400">
                  ${session.finalPrice.toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 mt-6 pt-4 border-t border-gray-800">
          {canStart && (
            <button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 transition"
            >
              {startMutation.isPending
                ? 'Starting...'
                : 'Start Negotiation'}
            </button>
          )}
          {!isTerminal && (
            <button
              onClick={() => terminateMutation.mutate()}
              disabled={terminateMutation.isPending}
              className="px-4 py-2 bg-red-600/20 text-red-400 border border-red-800 rounded-lg hover:bg-red-600/30 disabled:opacity-50 transition"
            >
              {terminateMutation.isPending ? 'Terminating...' : 'Terminate'}
            </button>
          )}
          {isTerminal && (
            <Link
              href={`/negotiations/${sessionId}/results`}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition"
            >
              View Results
            </Link>
          )}
        </div>

        {startMutation.isError && (
          <p className="text-red-400 text-sm mt-2">
            {startMutation.error instanceof Error
              ? startMutation.error.message
              : 'Failed to start negotiation'}
          </p>
        )}
      </div>

      {/* Negotiation timeline */}
      {(session.status === SessionStatus.NEGOTIATING ||
        session.status === SessionStatus.DEAL_REACHED ||
        session.status === SessionStatus.NO_DEAL) && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Negotiation Timeline
          </h2>
          <NegotiationTimeline proposals={[]} />
        </div>
      )}

      {/* Audit log */}
      <AuditLogViewer sessionId={sessionId} />
    </div>
  );
}
