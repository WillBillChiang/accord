import { SessionStatus } from '@/types/negotiation';

const statusConfig: Record<SessionStatus, { label: string; color: string }> = {
  [SessionStatus.AWAITING_PARTIES]: {
    label: 'Awaiting Parties',
    color: 'bg-yellow-900 text-yellow-300',
  },
  [SessionStatus.ONBOARDING]: {
    label: 'Onboarding',
    color: 'bg-blue-900 text-blue-300',
  },
  [SessionStatus.ZOPA_CHECK]: {
    label: 'Checking ZOPA',
    color: 'bg-purple-900 text-purple-300',
  },
  [SessionStatus.NEGOTIATING]: {
    label: 'Negotiating',
    color: 'bg-indigo-900 text-indigo-300',
  },
  [SessionStatus.DEAL_REACHED]: {
    label: 'Deal Reached',
    color: 'bg-green-900 text-green-300',
  },
  [SessionStatus.NO_DEAL]: {
    label: 'No Deal',
    color: 'bg-red-900 text-red-300',
  },
  [SessionStatus.EXPIRED]: {
    label: 'Expired',
    color: 'bg-gray-800 text-gray-400',
  },
  [SessionStatus.ERROR]: {
    label: 'Error',
    color: 'bg-red-900 text-red-300',
  },
};

export function SessionStatusBadge({ status }: { status: SessionStatus }) {
  const config = statusConfig[status] || {
    label: status,
    color: 'bg-gray-800 text-gray-400',
  };
  return (
    <span
      className={`px-3 py-1 rounded-full text-xs font-medium ${config.color}`}
    >
      {config.label}
    </span>
  );
}
