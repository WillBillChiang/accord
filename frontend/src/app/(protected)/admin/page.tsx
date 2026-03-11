'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { SessionStatus, type Session } from '@/types/negotiation';

export default function AdminPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: () => apiClient.listSessions(),
    refetchInterval: 10000,
  });

  const sessions = data?.sessions || [];

  const statusCounts = sessions.reduce(
    (acc: Record<string, number>, s: Session) => {
      acc[s.status] = (acc[s.status] || 0) + 1;
      return acc;
    },
    {}
  );

  const activeSessions = sessions.filter(
    (s: Session) =>
      s.status === SessionStatus.NEGOTIATING ||
      s.status === SessionStatus.ONBOARDING ||
      s.status === SessionStatus.ZOPA_CHECK
  ).length;

  const completedSessions = sessions.filter(
    (s: Session) =>
      s.status === SessionStatus.DEAL_REACHED ||
      s.status === SessionStatus.NO_DEAL
  ).length;

  const dealRate =
    completedSessions > 0
      ? (
          (sessions.filter(
            (s: Session) => s.status === SessionStatus.DEAL_REACHED
          ).length /
            completedSessions) *
          100
        ).toFixed(1)
      : '0';

  return (
    <div>
      <h1 className="text-2xl font-bold text-white mb-8">Admin Panel</h1>

      {isLoading ? (
        <div className="text-gray-400">Loading system status...</div>
      ) : (
        <>
          {/* Overview cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <p className="text-sm text-gray-400">Total Sessions</p>
              <p className="text-3xl font-bold text-white mt-1">
                {sessions.length}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <p className="text-sm text-gray-400">Active Sessions</p>
              <p className="text-3xl font-bold text-blue-400 mt-1">
                {activeSessions}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <p className="text-sm text-gray-400">Completed</p>
              <p className="text-3xl font-bold text-green-400 mt-1">
                {completedSessions}
              </p>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <p className="text-sm text-gray-400">Deal Rate</p>
              <p className="text-3xl font-bold text-purple-400 mt-1">
                {dealRate}%
              </p>
            </div>
          </div>

          {/* Status breakdown */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6 mb-8">
            <h2 className="text-lg font-semibold text-white mb-4">
              Sessions by Status
            </h2>
            <div className="space-y-3">
              {Object.values(SessionStatus).map((status) => {
                const count = statusCounts[status] || 0;
                const percentage =
                  sessions.length > 0
                    ? (count / sessions.length) * 100
                    : 0;
                return (
                  <div key={status} className="flex items-center gap-4">
                    <span className="text-gray-400 text-sm w-40 capitalize">
                      {status.replace(/_/g, ' ')}
                    </span>
                    <div className="flex-1 bg-gray-800 rounded-full h-2">
                      <div
                        className="bg-blue-600 rounded-full h-2 transition-all"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                    <span className="text-white text-sm w-8 text-right">
                      {count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* System health */}
          <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
            <h2 className="text-lg font-semibold text-white mb-4">
              System Health
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-green-400" />
                  <span className="text-sm text-gray-300">API Server</span>
                </div>
                <p className="text-xs text-gray-500">Operational</p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-green-400" />
                  <span className="text-sm text-gray-300">TEE Enclave</span>
                </div>
                <p className="text-xs text-gray-500">Operational</p>
              </div>
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-green-400" />
                  <span className="text-sm text-gray-300">Database</span>
                </div>
                <p className="text-xs text-gray-500">Operational</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
