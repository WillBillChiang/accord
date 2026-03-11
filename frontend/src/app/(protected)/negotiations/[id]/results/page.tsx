'use client';

import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { SessionStatusBadge } from '@/components/SessionStatusBadge';
import { AuditLogViewer } from '@/components/AuditLogViewer';
import { SessionStatus } from '@/types/negotiation';

export default function ResultsPage() {
  const params = useParams();
  const sessionId = params.id as string;

  const { data: session, isLoading } = useQuery({
    queryKey: ['session', sessionId],
    queryFn: () => apiClient.getSession(sessionId),
  });

  if (isLoading) {
    return <div className="text-gray-400">Loading results...</div>;
  }

  if (!session) {
    return (
      <div className="text-center py-20">
        <p className="text-red-400 mb-4">Session not found</p>
        <Link href="/dashboard" className="text-blue-400 hover:underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const isDeal = session.status === SessionStatus.DEAL_REACHED;
  const isNoDeal = session.status === SessionStatus.NO_DEAL;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <Link
          href={`/negotiations/${sessionId}`}
          className="text-gray-400 hover:text-white transition"
        >
          &larr; Back to Session
        </Link>
      </div>

      {/* Outcome header */}
      <div
        className={`rounded-xl border p-8 mb-6 text-center ${
          isDeal
            ? 'bg-green-950/20 border-green-800/30'
            : isNoDeal
              ? 'bg-red-950/20 border-red-800/30'
              : 'bg-gray-900 border-gray-800'
        }`}
      >
        <div className="mb-4">
          <SessionStatusBadge status={session.status} />
        </div>
        <h1
          className={`text-3xl font-bold mb-2 ${isDeal ? 'text-green-400' : isNoDeal ? 'text-red-400' : 'text-white'}`}
        >
          {isDeal
            ? 'Deal Reached'
            : isNoDeal
              ? 'No Deal'
              : session.status === SessionStatus.EXPIRED
                ? 'Session Expired'
                : 'Session Ended'}
        </h1>
        <p className="text-gray-400">
          Session {sessionId.slice(0, 8)}... has concluded
        </p>
      </div>

      {/* Deal details */}
      {isDeal && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Deal Summary
          </h2>
          <div className="grid grid-cols-2 gap-4">
            {session.finalPrice !== undefined && (
              <div className="bg-gray-800 rounded-lg p-4">
                <p className="text-sm text-gray-400">Final Price</p>
                <p className="text-2xl font-bold text-green-400">
                  ${session.finalPrice.toLocaleString()}
                </p>
              </div>
            )}
            {session.roundsCompleted !== undefined && (
              <div className="bg-gray-800 rounded-lg p-4">
                <p className="text-sm text-gray-400">Rounds Completed</p>
                <p className="text-2xl font-bold text-white">
                  {session.roundsCompleted}
                </p>
              </div>
            )}
          </div>

          {session.finalTerms &&
            Object.keys(session.finalTerms).length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide mb-3">
                  Agreed Terms
                </h3>
                <div className="bg-gray-800 rounded-lg p-4 space-y-2">
                  {Object.entries(session.finalTerms).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex justify-between items-center"
                    >
                      <span className="text-gray-300 text-sm">{key}</span>
                      <span className="text-white text-sm font-medium">
                        {String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
        </div>
      )}

      {/* No deal details */}
      {isNoDeal && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Outcome Details
          </h2>
          <div className="bg-gray-800 rounded-lg p-4">
            <p className="text-gray-300 text-sm">
              The negotiation concluded without reaching an agreement. All
              confidential data has been securely erased inside the TEE. You can
              verify this via attestation.
            </p>
          </div>
          {session.roundsCompleted !== undefined && (
            <div className="mt-4 bg-gray-800 rounded-lg p-4">
              <p className="text-sm text-gray-400">Rounds Completed</p>
              <p className="text-xl font-bold text-white">
                {session.roundsCompleted}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Audit log */}
      <div className="mb-6">
        <AuditLogViewer sessionId={sessionId} />
      </div>

      <div className="flex gap-3">
        <Link
          href="/attestation"
          className="px-4 py-2 border border-gray-700 text-gray-300 rounded-lg hover:border-gray-500 transition"
        >
          Verify Attestation
        </Link>
        <Link
          href="/dashboard"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
