export class NegotiationWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private onMessage: (data: unknown) => void;
  private reconnectAttempts = 0;
  private maxReconnects = 5;

  constructor(sessionId: string, onMessage: (data: unknown) => void) {
    this.sessionId = sessionId;
    this.onMessage = onMessage;
  }

  connect() {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8080';
    this.ws = new WebSocket(`${wsUrl}/ws/negotiations/${this.sessionId}`);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.onMessage(data);
      } catch (e) {
        console.error('WebSocket parse error:', e);
      }
    };

    this.ws.onclose = () => {
      if (this.reconnectAttempts < this.maxReconnects) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
      }
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
