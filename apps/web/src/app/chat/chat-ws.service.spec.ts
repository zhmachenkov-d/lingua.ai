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
});
