import type {
  CreateSessionRequest,
  OnboardPartyRequest,
  Session,
  NegotiationOutcome,
  AttestationDocument,
  AuditLogEntry,
} from '@/types/negotiation';
import { auth } from './firebase';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async getAuthToken(): Promise<string | null> {
    const currentUser = auth.currentUser;
    if (!currentUser) return null;
    return currentUser.getIdToken();
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await this.getAuthToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `API error: ${response.status}`);
    }

    return response.json();
  }

  // Sessions
  async createSession(data: CreateSessionRequest) {
    return this.request<{ session_id: string; status: string; created_at: number }>(
      '/api/v1/sessions',
      { method: 'POST', body: JSON.stringify(data) }
    );
  }

  async listSessions() {
    return this.request<{ sessions: Session[] }>('/api/v1/sessions');
  }

  async getSession(sessionId: string) {
    return this.request<Session>(`/api/v1/sessions/${sessionId}`);
  }

  async terminateSession(sessionId: string) {
    return this.request(`/api/v1/sessions/${sessionId}`, { method: 'DELETE' });
  }

  // Onboarding
  async onboardParty(sessionId: string, data: OnboardPartyRequest) {
    return this.request(`/api/v1/sessions/${sessionId}/onboard`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Negotiation
  async startNegotiation(sessionId: string) {
    return this.request<NegotiationOutcome>(`/api/v1/sessions/${sessionId}/start`, {
      method: 'POST',
    });
  }

  async getNegotiationStatus(sessionId: string) {
    return this.request(`/api/v1/sessions/${sessionId}/status`);
  }

  // Attestation
  async getAttestation(nonce?: string) {
    const query = nonce ? `?nonce=${nonce}` : '';
    return this.request<AttestationDocument>(`/api/v1/attestation${query}`);
  }

  async verifyAttestation(
    expectedPcr0: string,
    expectedPcr1?: string,
    expectedPcr2?: string
  ) {
    return this.request<{ verified: boolean }>('/api/v1/attestation/verify', {
      method: 'POST',
      body: JSON.stringify({
        expected_pcr0: expectedPcr0,
        expected_pcr1: expectedPcr1,
        expected_pcr2: expectedPcr2,
      }),
    });
  }

  // Audit
  async getSessionAuditLog(sessionId: string) {
    return this.request<{ audit_logs: AuditLogEntry[] }>(
      `/api/v1/sessions/${sessionId}/audit`
    );
  }
}

export const apiClient = new ApiClient();
export type { ApiClient };
