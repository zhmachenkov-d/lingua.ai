import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import { ChatShell, TURN_IDLE_MS } from './chat-shell';
import {
  MAX_MESSAGE_LENGTH,
  NETWORK_FAIL,
  PASTE_TOO_LONG,
  SOON_LABEL,
  UNPARSEABLE_FRAME,
} from './chat.copy';
import { WEB_SOCKET_FACTORY, WS_URL } from './chat-ws.tokens';
import { MockWebSocket } from './mock-web-socket';

describe('ChatShell', () => {
  let fixture: ComponentFixture<ChatShell>;
  let latestSocket: MockWebSocket | null;

  beforeEach(async () => {
    latestSocket = null;
    await TestBed.configureTestingModule({
      imports: [ChatShell],
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
    }).compileComponents();

    fixture = TestBed.createComponent(ChatShell);
    fixture.detectChanges();
    latestSocket!.simulateOpen();
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
    fixture.destroy();
  });

  it('blocks over-length paste with paste-too-long and sends no WS frame', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('x'.repeat(MAX_MESSAGE_LENGTH + 1));
    shell['send']();
    fixture.detectChanges();

    expect(shell['localError']()).toBe(PASTE_TOO_LONG);
    expect(latestSocket!.sent).toEqual([]);
    expect(shell['inFlight']()).toBe(false);
  });

  it('sends turn_request and renders turn_complete with disabled CTAs', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('привет');
    shell['send']();
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(true);
    expect(latestSocket!.sent).toHaveLength(1);
    const frame = JSON.parse(latestSocket!.sent[0]!);
    expect(frame.kind).toBe('turn_request');
    expect(frame.text).toBe('привет');
    expect(fixture.nativeElement.textContent).toContain('привет');

    latestSocket!.simulateMessage({
      kind: 'turn_complete',
      message: 'Выберите агента',
      ctas: ['tutor', 'vocabulary', 'review'],
      clarify: null,
      backup_notice: null,
      turn_id: frame.turn_id,
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Выберите агента');
    expect(text).toContain('Tutor');
    expect(text).toContain('Vocabulary');
    expect(text).toContain('Review');
    expect(text).toContain(SOON_LABEL);

    const ctaButtons = fixture.debugElement.queryAll(By.css('.cta'));
    expect(ctaButtons).toHaveLength(3);
    for (const btn of ctaButtons) {
      expect((btn.nativeElement as HTMLButtonElement).disabled).toBe(true);
      expect(btn.attributes['aria-disabled']).toBe('true');
    }
  });

  it('ignores token_delta (no bubble)', () => {
    const shell = fixture.componentInstance;
    const before = shell['bubbles']().length;
    latestSocket!.simulateMessage({ kind: 'token_delta', text: 'stream' });
    fixture.detectChanges();
    expect(shell['bubbles']().length).toBe(before);
  });

  it('blocks second send while in flight', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('one');
    shell['send']();
    shell['draft'].set('two');
    shell['send']();
    expect(latestSocket!.sent).toHaveLength(1);
  });

  it('clears in-flight and shows network-fail on mid-turn socket close', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('pending');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);

    latestSocket!.simulateAbnormalClose();
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(shell['showNetworkFail']()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain(NETWORK_FAIL);
    expect(fixture.nativeElement.textContent).toContain('Повторить');
  });

  it('clears in-flight and shows network-fail when idle watchdog fires', () => {
    vi.useFakeTimers();
    const shell = fixture.componentInstance;
    shell['draft'].set('pending');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);
    expect(shell['showNetworkFail']()).toBe(false);

    vi.advanceTimersByTime(TURN_IDLE_MS - 1);
    expect(shell['inFlight']()).toBe(true);

    vi.advanceTimersByTime(1);
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(shell['showNetworkFail']()).toBe(true);
    expect(shell['composerDisabled']).toBe(true);
    expect(fixture.nativeElement.textContent).toContain(NETWORK_FAIL);
    expect(fixture.nativeElement.textContent).toContain('Повторить');
  });

  it('cancels idle watchdog when a matching terminal arrives', () => {
    vi.useFakeTimers();
    const shell = fixture.componentInstance;
    shell['draft'].set('ok');
    shell['send']();
    const frame = JSON.parse(latestSocket!.sent[0]!);

    vi.advanceTimersByTime(TURN_IDLE_MS / 2);
    latestSocket!.simulateMessage({
      kind: 'turn_complete',
      message: 'done',
      ctas: ['tutor'],
      clarify: null,
      backup_notice: null,
      turn_id: frame.turn_id,
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(shell['showNetworkFail']()).toBe(false);

    vi.advanceTimersByTime(TURN_IDLE_MS);
    fixture.detectChanges();

    expect(shell['showNetworkFail']()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('done');
  });

  it('ignores late terminals after idle watchdog shows network-fail', () => {
    vi.useFakeTimers();
    const shell = fixture.componentInstance;
    shell['draft'].set('pending');
    shell['send']();
    const frame = JSON.parse(latestSocket!.sent[0]!);
    const beforeBubbles = shell['bubbles']().length;

    vi.advanceTimersByTime(TURN_IDLE_MS);
    fixture.detectChanges();
    expect(shell['showNetworkFail']()).toBe(true);

    latestSocket!.simulateMessage({
      kind: 'turn_complete',
      message: 'late complete',
      ctas: ['tutor'],
      clarify: null,
      backup_notice: null,
      turn_id: frame.turn_id,
    });
    fixture.detectChanges();

    expect(shell['showNetworkFail']()).toBe(true);
    expect(shell['bubbles']().length).toBe(beforeBubbles);
    expect(shell['ctas']()).toEqual([]);
    expect(fixture.nativeElement.textContent).not.toContain('late complete');
    expect(fixture.nativeElement.textContent).not.toContain('Tutor');
  });

  it('shows network-fail and Повторить on connect fail / 409 without stub turns', () => {
    const beforeBubbles = fixture.componentInstance['bubbles']().length;
    latestSocket!.simulateAbnormalClose();
    fixture.detectChanges();

    expect(fixture.componentInstance['inFlight']()).toBe(false);
    expect(fixture.componentInstance['showNetworkFail']()).toBe(true);
    expect(fixture.nativeElement.textContent).toContain(NETWORK_FAIL);
    expect(fixture.nativeElement.textContent).toContain('Повторить');
    expect(fixture.componentInstance['bubbles']().length).toBe(beforeBubbles);
    expect(latestSocket!.sent).toEqual([]);
  });

  it('shows server error message and re-enables composer', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('x');
    shell['send']();
    const frame = JSON.parse(latestSocket!.sent[0]!);
    latestSocket!.simulateMessage({
      kind: 'error',
      message: 'Языковая модель сейчас недоступна. Попробуйте позже.',
      code: 'llm_unavailable',
      turn_id: frame.turn_id,
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain(
      'Языковая модель сейчас недоступна. Попробуйте позже.',
    );
    expect(shell['composerDisabled']).toBe(false);
  });

  it('clears in-flight on unknown-code error and re-enables composer', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('x');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);
    const frame = JSON.parse(latestSocket!.sent[0]!);

    latestSocket!.simulateMessage({
      kind: 'error',
      message: 'Unexpected failure',
      code: 'future_code',
      turn_id: frame.turn_id,
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('Unexpected failure');
    expect(shell['composerDisabled']).toBe(false);
  });

  it('keeps in-flight on turn_complete with mismatched or missing turn_id', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('pending');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);
    const beforeBubbles = shell['bubbles']().length;

    latestSocket!.simulateMessage({
      kind: 'turn_complete',
      message: 'stale complete',
      ctas: ['tutor'],
      clarify: null,
      backup_notice: null,
      turn_id: 'other-turn',
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(true);
    expect(shell['composerDisabled']).toBe(true);
    expect(shell['bubbles']().length).toBe(beforeBubbles);
    expect(shell['ctas']()).toEqual([]);
    expect(fixture.nativeElement.textContent).not.toContain('stale complete');
    expect(fixture.nativeElement.textContent).not.toContain('Tutor');

    latestSocket!.simulateMessage({
      kind: 'turn_complete',
      message: 'no id complete',
      ctas: ['tutor'],
      clarify: null,
      backup_notice: null,
      turn_id: null,
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(true);
    expect(shell['bubbles']().length).toBe(beforeBubbles);
    expect(shell['ctas']()).toEqual([]);
    expect(fixture.nativeElement.textContent).not.toContain('no id complete');
    expect(fixture.nativeElement.textContent).not.toContain('Tutor');
  });

  it('keeps in-flight on error with mismatched or missing turn_id', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('pending');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);
    const beforeBubbles = shell['bubbles']().length;

    latestSocket!.simulateMessage({
      kind: 'error',
      message: 'overlap',
      code: 'invalid_turn_request',
      turn_id: 'foreign',
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(true);
    expect(shell['bubbles']().length).toBe(beforeBubbles);

    latestSocket!.simulateMessage({
      kind: 'error',
      message: 'no id',
      code: 'llm_unavailable',
      turn_id: null,
    });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(true);
    expect(shell['composerDisabled']).toBe(true);
    expect(shell['bubbles']().length).toBe(beforeBubbles);
  });

  it('clears in-flight on malformed frame while waiting for a terminal event', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('x');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);

    latestSocket!.simulateMessage('not-json');
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain(UNPARSEABLE_FRAME);
    expect(shell['composerDisabled']).toBe(false);
  });

  it('clears in-flight on terminal-shaped frames that fail parse', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('x');
    shell['send']();
    expect(shell['inFlight']()).toBe(true);

    // turn_complete without ctas → parse null → undeliverable$
    latestSocket!.simulateMessage({ kind: 'turn_complete', message: 'incomplete' });
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain(UNPARSEABLE_FRAME);
    expect(shell['composerDisabled']).toBe(false);
  });

  it('ignores undeliverable frames when no turn is in flight', () => {
    const shell = fixture.componentInstance;
    const before = shell['bubbles']().length;

    latestSocket!.simulateMessage('not-json');
    fixture.detectChanges();

    expect(shell['inFlight']()).toBe(false);
    expect(shell['bubbles']().length).toBe(before);
    expect(fixture.nativeElement.textContent).not.toContain(UNPARSEABLE_FRAME);
  });

  it('renders blank-path server message as-is (no client blank-input rewrite)', () => {
    const shell = fixture.componentInstance;
    shell['draft'].set('   ');
    shell['send']();
    const frame = JSON.parse(latestSocket!.sent[0]!);
    expect(frame.text).toBe('');
    expect(shell['bubbles']().filter((b: { role: string }) => b.role === 'outbound')).toEqual([]);

    latestSocket!.simulateMessage({
      kind: 'turn_complete',
      message: 'Выберите, чем заняться: Tutor (урок), Vocabulary (слова) или Review (повторение).',
      ctas: ['tutor', 'vocabulary', 'review'],
      clarify: null,
      backup_notice: null,
      turn_id: frame.turn_id,
    });
    fixture.detectChanges();

    expect(shell['bubbles']().filter((b: { role: string }) => b.role === 'outbound')).toEqual([]);
    expect(fixture.nativeElement.textContent).toContain(
      'Выберите, чем заняться: Tutor (урок), Vocabulary (слова) или Review (повторение).',
    );
    expect(fixture.nativeElement.textContent).not.toContain('Напиши сообщение или выбери агента.');
  });

  it('on !sent shows network-fail without orphan outbound and locks composer', () => {
    const shell = fixture.componentInstance;
    latestSocket!.readyState = MockWebSocket.CLOSED;
    shell['draft'].set('lost');
    shell['send']();
    fixture.detectChanges();

    expect(latestSocket!.sent).toEqual([]);
    expect(shell['bubbles']()).toEqual([]);
    expect(shell['draft']()).toBe('lost');
    expect(shell['showNetworkFail']()).toBe(true);
    expect(shell['composerDisabled']).toBe(true);
    expect(fixture.nativeElement.textContent).toContain(NETWORK_FAIL);
  });
});
