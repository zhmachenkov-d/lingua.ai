import { DestroyRef, Injectable, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';

import type { ServerEvent, TurnRequest } from './chat.types';
import { WS_ALREADY_OPEN_CLOSE_CODE } from './chat.types';
import { WEB_SOCKET_FACTORY, WS_URL } from './chat-ws.tokens';

export type ChatWsConnectionState = 'idle' | 'connecting' | 'open' | 'failed' | 'conflict';

/**
 * Single-socket AD-6 client. Emits parsed server events.
 * Malformed frames notify `undeliverable$` so an in-flight turn can recover.
 * `token_delta` is parsed and forwarded so callers can ignore without bubbling UI.
 */
@Injectable({ providedIn: 'root' })
export class ChatWsService {
  private readonly url = inject(WS_URL);
  private readonly createSocket = inject(WEB_SOCKET_FACTORY);
  private readonly destroyRef = inject(DestroyRef);

  private socket: WebSocket | null = null;
  private intentionalClose = false;
  /** Set when a `ws_already_open` error frame arrives before the conflict close. */
  private sawSingletonConflict = false;

  private readonly eventsSubject = new Subject<ServerEvent>();
  readonly events$ = this.eventsSubject.asObservable();

  private readonly undeliverableSubject = new Subject<void>();
  /** Fired when a socket message could not be parsed into a ServerEvent. */
  readonly undeliverable$ = this.undeliverableSubject.asObservable();

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
    this.sawSingletonConflict = false;
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
      if (!parsed) {
        this.undeliverableSubject.next();
        return;
      }
      if (parsed.kind === 'error' && parsed.code === 'ws_already_open') {
        // Mark conflict immediately so the shell does not treat the rejectee as sendable
        // before close(4009); close-code path remains a fallback.
        this.sawSingletonConflict = true;
        this.connectionState.set('conflict');
        return;
      }
      this.eventsSubject.next(parsed);
    });

    socket.addEventListener('error', () => {
      if (this.socket !== socket) {
        return;
      }
      // Close / fail path finalized in `close` (browsers fire both on connect fail).
    });

    socket.addEventListener('close', (event: CloseEvent) => {
      if (this.socket !== socket) {
        return;
      }
      this.socket = null;
      if (!this.intentionalClose) {
        if (this.sawSingletonConflict || event.code === WS_ALREADY_OPEN_CLOSE_CODE) {
          this.connectionState.set('conflict');
        } else {
          this.connectionState.set('failed');
        }
      } else if (this.connectionState() !== 'failed' && this.connectionState() !== 'conflict') {
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
    // Clear open state here: nulling socket first makes the close-event identity
    // guard skip, which would otherwise leave connectionState stuck at open.
    if (this.connectionState() !== 'failed' && this.connectionState() !== 'conflict') {
      this.connectionState.set('idle');
    }
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
    // Accept any string code — unknown codes must still clear in-flight in the shell.
    if (typeof message !== 'string' || typeof code !== 'string' || code.length === 0) {
      return null;
    }
    const turnId = (data as { turn_id?: unknown }).turn_id;
    return {
      kind: 'error',
      message,
      code,
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
