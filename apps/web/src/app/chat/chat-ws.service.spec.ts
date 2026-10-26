import { TestBed } from '@angular/core/testing';

import { ChatWsService, parseServerEvent } from './chat-ws.service';
import { WEB_SOCKET_FACTORY, WS_URL } from './chat-ws.tokens';
import { MockWebSocket } from './mock-web-socket';

describe('parseServerEvent', () => {
  it('parses turn_complete', () => {
    const event = parseServerEvent(
      JSON.stringify({
        kind: 'turn_complete',
        message: 'Выберите',
        ctas: ['tutor', 'vocabulary', 'review'],
        clarify: null,
        backup_notice: null,
        turn_id: 't1',
      }),
    );
    expect(event).toEqual({
      kind: 'turn_complete',
      message: 'Выберите',
      ctas: ['tutor', 'vocabulary', 'review'],
      clarify: null,
      backup_notice: null,
      turn_id: 't1',
    });
  });

  it('parses token_delta so callers can ignore it', () => {
    const event = parseServerEvent(
      JSON.stringify({ kind: 'token_delta', text: 'hi', turn_id: 't1' }),
    );
    expect(event).toEqual({ kind: 'token_delta', text: 'hi', turn_id: 't1' });
  });

  it('returns null for malformed frames', () => {
    expect(parseServerEvent('not-json')).toBeNull();
    expect(parseServerEvent(JSON.stringify({ kind: 'turn_complete' }))).toBeNull();
  });

  it('parses error with a known code', () => {
    const event = parseServerEvent(
      JSON.stringify({
        kind: 'error',
        message: 'Языковая модель сейчас недоступна. Попробуйте позже.',
        code: 'llm_unavailable',
        turn_id: 't1',
      }),
    );
    expect(event).toEqual({
      kind: 'error',
      message: 'Языковая модель сейчас недоступна. Попробуйте позже.',
      code: 'llm_unavailable',
      turn_id: 't1',
    });
  });

  it('parses error with an unknown code (does not drop)', () => {
    const event = parseServerEvent(
      JSON.stringify({
        kind: 'error',
        message: 'Unexpected failure',
        code: 'future_code',
        turn_id: 't1',
      }),
    );
    expect(event).toEqual({
      kind: 'error',
      message: 'Unexpected failure',
      code: 'future_code',
      turn_id: 't1',
    });
  });

  it('returns null for error missing message or empty code', () => {
    expect(parseServerEvent(JSON.stringify({ kind: 'error', code: 'llm_unavailable' }))).toBeNull();
    expect(parseServerEvent(JSON.stringify({ kind: 'error', message: 'x', code: '' }))).toBeNull();
  });
});

describe('ChatWsService', () => {
  let latestSocket: MockWebSocket | null;

  beforeEach(() => {
    latestSocket = null;
    TestBed.configureTestingModule({
      providers: [
        { provide: WS_URL, useValue: 'ws://test.example:8000/ws' },
        {
          provide: WEB_SOCKET_FACTORY,
          useValue: (url: string) => {
            latestSocket = new MockWebSocket(url);
            return latestSocket as unknown as WebSocket;
          },
        },
      ],
    });
  });

  it('connects and sends turn_request', () => {
    const service = TestBed.inject(ChatWsService);
    service.connect();
    expect(latestSocket).toBeTruthy();
    latestSocket!.simulateOpen();
    expect(service.connectionState()).toBe('open');

    const ok = service.sendTurn('hello', 'tid');
    expect(ok).toBe(true);
    expect(JSON.parse(latestSocket!.sent[0]!)).toEqual({
      kind: 'turn_request',
      text: 'hello',
      turn_id: 'tid',
    });
  });

  it('marks failed on abnormal close (connect fail / 409)', () => {
    const service = TestBed.inject(ChatWsService);
    service.connect();
    latestSocket!.simulateAbnormalClose();
    expect(service.connectionState()).toBe('failed');
  });

  it('retry opens a new socket without auto-loop', () => {
    const service = TestBed.inject(ChatWsService);
    service.connect();
    const first = latestSocket!;
    first.simulateAbnormalClose();
    service.retry();
    expect(latestSocket).not.toBe(first);
    expect(service.connectionState()).toBe('connecting');
  });

  it('emits undeliverable$ for malformed frames and events$ for unknown-code errors', () => {
    const service = TestBed.inject(ChatWsService);
    const events: unknown[] = [];
    const undeliverable: number[] = [];
    service.events$.subscribe((e) => events.push(e));
    service.undeliverable$.subscribe(() => undeliverable.push(1));

    service.connect();
    latestSocket!.simulateOpen();
    latestSocket!.simulateMessage('not-json');
    expect(undeliverable).toHaveLength(1);
    expect(events).toHaveLength(0);

    latestSocket!.simulateMessage({
      kind: 'error',
      message: 'Unexpected',
      code: 'future_code',
    });
    expect(events).toEqual([
      { kind: 'error', message: 'Unexpected', code: 'future_code', turn_id: null },
    ]);
    expect(undeliverable).toHaveLength(1);
  });
});
