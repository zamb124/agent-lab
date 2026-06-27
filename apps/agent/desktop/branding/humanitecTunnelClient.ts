import type { HumanitecAgentCredentials } from './humanitecAgentStore';

type WebSocketLike = {
  readyState: number;
  send(data: string): void;
  close(): void;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
};

const WS_OPEN = 1;

function createWebSocket(url: string): WebSocketLike {
  const WebSocketCtor = globalThis.WebSocket;
  if (typeof WebSocketCtor === 'undefined') {
    throw new Error('WebSocket is not available in this runtime');
  }
  return new WebSocketCtor(url) as unknown as WebSocketLike;
}

export type HumanitecTunnelClientOptions = {
  credentials: HumanitecAgentCredentials;
  onPolicy?: (policy: Record<string, unknown>) => void;
  onDisconnected?: (code: number, reason: string) => void;
  log?: (message: string) => void;
};

type JsonRpcResponsePayload = {
  result?: Record<string, unknown>;
  error?: { message?: string; code?: number };
};

export class HumanitecTunnelClient {
  private socket: WebSocketLike | null = null;

  constructor(private readonly options: HumanitecTunnelClientOptions) {}

  connect(): void {
    if (this.socket !== null) {
      return;
    }
    const token = this.options.credentials.token;
    const wsUrl = `${this.options.credentials.tunnel_ws_url}?token=${encodeURIComponent(token)}`;
    const socket = createWebSocket(wsUrl);
    this.socket = socket;

    socket.onopen = () => {
      this.options.log?.('humanitec tunnel connected');
    };

    socket.onmessage = (event) => {
      const text = typeof event.data === 'string' ? event.data : String(event.data);
      let payload: Record<string, unknown>;
      try {
        payload = JSON.parse(text) as Record<string, unknown>;
      } catch {
        throw new Error('humanitec tunnel: invalid JSON frame');
      }
      this.handleFrame(payload);
    };

    socket.onclose = (event) => {
      this.socket = null;
      const reason = event.reason;
      this.options.onDisconnected?.(event.code, reason);
    };

    socket.onerror = () => {
      this.options.log?.('humanitec tunnel error');
    };
  }

  disconnect(): void {
    if (this.socket === null) {
      return;
    }
    this.socket.close();
    this.socket = null;
  }

  sendPing(): void {
    this.sendFrame({ type: 'ping' });
  }

  sendMcpResponse(requestId: string, result: Record<string, unknown>): void {
    this.sendFrame({
      type: 'mcp_response',
      request_id: requestId,
      result,
    });
  }

  private sendFrame(frame: Record<string, unknown>): void {
    if (this.socket === null || this.socket.readyState !== WS_OPEN) {
      throw new Error('humanitec tunnel is not connected');
    }
    this.socket.send(JSON.stringify(frame));
  }

  private handleFrame(payload: Record<string, unknown>): void {
    const frameType = payload.type;
    if (frameType === 'policy') {
      const policy = payload.policy;
      if (typeof policy !== 'object' || policy === null) {
        throw new Error('humanitec tunnel policy frame invalid');
      }
      this.options.onPolicy?.(policy as Record<string, unknown>);
      return;
    }
    if (frameType === 'pong') {
      return;
    }
    if (frameType === 'mcp_request') {
      const requestId = payload.request_id;
      if (typeof requestId !== 'string' || !requestId) {
        throw new Error('humanitec tunnel mcp_request without request_id');
      }
      const method = payload.method;
      const params = payload.params;
      if (typeof method !== 'string' || !method) {
        throw new Error('humanitec tunnel mcp_request without method');
      }
      if (typeof params !== 'object' || params === null) {
        throw new Error('humanitec tunnel mcp_request params must be object');
      }
      void this.handleMcpRequest(requestId, method, params as Record<string, unknown>);
      return;
    }
    if (frameType === 'error') {
      const detail = payload.detail;
      if (typeof detail === 'string' && detail) {
        throw new Error(`humanitec tunnel error frame: ${detail}`);
      }
      throw new Error('humanitec tunnel error frame');
    }
  }

  private async forwardToLocalMcp(
    method: string,
    params: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const localMcpUrl = process.env.HUMANITEC_LOCAL_MCP_URL;
    if (typeof localMcpUrl !== 'string' || !localMcpUrl.trim()) {
      throw new Error('HUMANITEC_LOCAL_MCP_URL is not configured');
    }
    const response = await fetch(localMcpUrl.trim(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.options.credentials.token}`,
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 'humanitec-tunnel',
        method,
        params,
      }),
    });
    if (!response.ok) {
      throw new Error(`local MCP HTTP ${response.status}`);
    }
    const body = (await response.json()) as JsonRpcResponsePayload;
    if (body.error) {
      const message = body.error.message;
      if (typeof message === 'string' && message) {
        throw new Error(message);
      }
      throw new Error('local MCP returned error');
    }
    if (typeof body.result !== 'object' || body.result === null) {
      throw new Error('local MCP response without result');
    }
    return body.result;
  }

  private async handleMcpRequest(
    requestId: string,
    method: string,
    params: Record<string, unknown>,
  ): Promise<void> {
    try {
      const localMcpUrl = process.env.HUMANITEC_LOCAL_MCP_URL;
      if (typeof localMcpUrl === 'string' && localMcpUrl.trim()) {
        const result = await this.forwardToLocalMcp(method, params);
        this.sendMcpResponse(requestId, result);
        return;
      }
      if (method === 'tools/list') {
        this.sendMcpResponse(requestId, { tools: [] });
        return;
      }
      this.sendFrame({
        type: 'mcp_response',
        request_id: requestId,
        error_detail: `device MCP unavailable for method: ${method}`,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      this.sendFrame({
        type: 'mcp_response',
        request_id: requestId,
        error_detail: detail,
      });
    }
  }
}
