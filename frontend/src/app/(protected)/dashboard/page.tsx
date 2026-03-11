'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { apiClient } from '@/lib/api-client';
import { SessionStatusBadge } from '@/components/SessionStatusBadge';
import type { Session } from '@/types/negotiation';

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => apiClient.listSessions(),
  });

  const sessions = data?.sessions || [];

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-2xl font-bold text-white">Negotiations</h1>
        <Link
          href="/negotiations/new"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition"
        >
          New Negotiation
        </Link>
      </div>

      {isLoading ? (
        <div className="text-gray-400">Loading sessions...</div>
      ) : error ? (
        <div className="text-red-400">
          Failed to load sessions. Please try again.
        </div>
      ) : sessions.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-gray-400 mb-4">No negotiations yet</p>
          <Link
            href="/negotiations/new"
            className="text-blue-400 hover:underline"
          >
            Create your first negotiation
          </Link>
        </div>
      ) : (
        <div className="grid gap-4">
          {sessions.map((session: Session) => (
            <Link
              key={session.sessionId}
              href={`/negotiations/${session.sessionId}`}
              className="bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-gray-700 transition block"
            >
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="text-white font-medium">
                    {session.description || session.sessionId}
                  </h3>
                  <p className="text-gray-500 text-sm mt-1">
                    {session.useCase || 'General negotiation'} &middot; Created{' '}
                    {new Date(session.createdAt * 1000).toLocaleDateString()}
                  </p>
                </div>
                <SessionStatusBadge status={session.status} />
              </div>
              <div className="flex gap-4 mt-4 text-sm text-gray-400">
                <span>
                  Seller: {session.sellerOnboarded ? 'Ready' : 'Pending'}
                </span>
                <span>
                  Buyer: {session.buyerOnboarded ? 'Ready' : 'Pending'}
                </span>
                {session.roundsCompleted !== undefined && (
                  <span>Rounds: {session.roundsCompleted}</span>
                )}
                {session.finalPrice !== undefined && (
                  <span className="text-green-400">
                    Final: ${session.finalPrice.toLocaleString()}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
