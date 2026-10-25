import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';

import type { ErrorCode, ServerEvent, TurnRequest } from './chat.types';
import { WEB_SOCKET_FACTORY, WS_URL } from './chat-ws.tokens';

const ERROR_CODES = new Set<string>([
  'llm_misconfigured',
  'llm_unavailable',
  'invalid_turn_request',
  'checkpointer_write_failed',
]);

export type ChatWsConnectionState = 'idle' | 'connecting' | 'open' | 'failed';

/**
 * Single-socket AD-6 client. Emits parsed server events; ignores malformed frames.
 * `token_delta` is parsed and forwarded so callers can ignore without bubbling UI.
 */
@Injectable({ providedIn: 'root' })
export class ChatWsService {
  private readonly url = inject(WS_URL);
  private readonly createSocket = inject(WEB_SOCKET_FACTORY);
  private readonly destroyRef = inject(DestroyRef);

  private socket: WebSocket | null = null;
  private intentionalClose = false;

  private readonly eventsSubject = new Subject<ServerEvent>();
  readonly events$ = this.eventsSubject.asObservable();

  readonly connectionState = signal<ChatWsConnectionState>('idle');

  constructor() {
    this.destroyRef.onDestroy(() => this.close());
  }

  connect(): void {
    if (
      this.socket &&
      (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.intentionalClose = false;
    this.connectionState.set('connecting');

    let socket: WebSocket;
    try {
      socket = this.createSocket(this.url);
    } catch {
      this.socket = null;
      this.connectionState.set('failed');
      return;
    }

    this.socket = socket;

    socket.addEventListener('open', () => {
      if (this.socket !== socket) {
        return;
      }
      this.connectionState.set('open');
    });

    socket.addEventListener('message', (event: MessageEvent<string>) => {
      if (this.socket !== socket) {
        return;
      }
      const parsed = parseServerEvent(event.data);
      if (parsed) {
        this.eventsSubject.next(parsed);
      }
    });

    socket.addEventListener('error', () => {
      if (this.socket !== socket) {
        return;
      }
      // Close / fail path finalized in `close` (browsers fire both on 409 / connect fail).
    });

    socket.addEventListener('close', () => {
      if (this.socket !== socket) {
        return;
      }
      this.socket = null;
      if (!this.intentionalClose) {
        this.connectionState.set('failed');
      } else if (this.connectionState() !== 'failed') {
        this.connectionState.set('idle');
      }
    });
  }

  /** Manual retry — no auto-reconnect loop. */
  retry(): void {
    this.close();
    this.connect();
  }

  sendTurn(text: string, turnId?: string): boolean {
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }
    const payload: TurnRequest = { kind: 'turn_request', text };
    if (turnId !== undefined) {
      payload.turn_id = turnId;
    }
    socket.send(JSON.stringify(payload));
    return true;
  }

  close(): void {
    this.intentionalClose = true;
    const socket = this.socket;
    this.socket = null;
    if (socket && socket.readyState < WebSocket.CLOSING) {
      socket.close();
    }
  }
}

export function parseServerEvent(raw: string): ServerEvent | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object') {
    return null;
  }
  const kind = (data as { kind?: unknown }).kind;
  if (kind === 'turn_complete') {
    const message = (data as { message?: unknown }).message;
    const ctas = (data as { ctas?: unknown }).ctas;
    if (typeof message !== 'string' || !Array.isArray(ctas)) {
      return null;
    }
    if (!ctas.every((c): c is string => typeof c === 'string')) {
      return null;
    }
    const backup = (data as { backup_notice?: unknown }).backup_notice;
    const turnId = (data as { turn_id?: unknown }).turn_id;
    return {
      kind: 'turn_complete',
      message,
      ctas,
      clarify: null,
      backup_notice: typeof backup === 'string' ? backup : null,
      turn_id: typeof turnId === 'string' ? turnId : null,
    };
  }
  if (kind === 'error') {
    const message = (data as { message?: unknown }).message;
    const code = (data as { code?: unknown }).code;
    if (typeof message !== 'string' || typeof code !== 'string' || !ERROR_CODES.has(code)) {
      return null;
    }
    const turnId = (data as { turn_id?: unknown }).turn_id;
    return {
      kind: 'error',
      message,
      code: code as ErrorCode,
      turn_id: typeof turnId === 'string' ? turnId : null,
    };
  }
  if (kind === 'token_delta') {
    const text = (data as { text?: unknown }).text;
    const turnId = (data as { turn_id?: unknown }).turn_id;
    return {
      kind: 'token_delta',
      text: typeof text === 'string' ? text : '',
      turn_id: typeof turnId === 'string' ? turnId : null,
    };
  }
  return null;
}
