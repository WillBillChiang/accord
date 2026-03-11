'use client';

import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { AuditLogEntry } from '@/types/negotiation';

export function AuditLogViewer({ sessionId }: { sessionId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['audit', sessionId],
    queryFn: () => apiClient.getSessionAuditLog(sessionId),
  });

  const logs = data?.audit_logs || [];

  if (isLoading)
    return <div className="text-gray-400">Loading audit log...</div>;

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800">
      <div className="p-4 border-b border-gray-800">
        <h3 className="text-white font-medium">Audit Log</h3>
      </div>
      <div className="divide-y divide-gray-800">
        {logs.length === 0 ? (
          <div className="p-4 text-gray-500 text-sm">No audit entries</div>
        ) : (
          logs.map((entry: AuditLogEntry) => (
            <div
              key={entry.auditId}
              className="p-4 flex justify-between items-center"
            >
              <div>
                <span className="text-white text-sm">{entry.action}</span>
                <span className="text-gray-500 text-xs ml-2">
                  by {entry.userId}
                </span>
              </div>
              <span className="text-gray-500 text-xs">
                {new Date(entry.timestamp * 1000).toLocaleString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
