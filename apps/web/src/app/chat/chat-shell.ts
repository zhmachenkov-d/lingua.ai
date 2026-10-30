import { Component, DestroyRef, OnInit, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import {
  BRAND_NAME,
  COMPOSER_PLACEHOLDER,
  MAX_MESSAGE_LENGTH,
  NETWORK_FAIL,
  PASTE_TOO_LONG,
  RETRY_LABEL,
  SEND_LABEL,
  UNPARSEABLE_FRAME,
  WS_ALREADY_OPEN,
} from './chat.copy';
import { ChatWsService } from './chat-ws.service';
import { CTA_INTENT, mapCtaIds } from './cta-labels';
import type { ChatBubble, CtaChip, CtaId, ServerEvent } from './chat.types';

/**
 * Idle ms with no matching terminal event before network-fail recovery (#60 / #111).
 * Must stay strictly above server turn wall-clock worst case:
 * 2×REQUEST_TIMEOUT_SECONDS (primary+escalate) + 2×CHECKPOINTER_WRITE_TIMEOUT_SECONDS
 * (snapshot then session-mirror) = 120s, plus a small delivery margin.
 */
export const TURN_IDLE_MS = 125_000;

/** MVP Verify unit chrome refs (no list API). */
export const CHROME_READY_SB_REF = 'ef4-beg-sb/1A';
export const CHROME_WORKBOOK_REF = 'ef4-beg-wb/1A';

@Component({
  selector: 'app-chat-shell',
  imports: [FormsModule],
  templateUrl: './chat-shell.html',
  styleUrl: './chat-shell.css',
})
export class ChatShell implements OnInit {
  private readonly ws = inject(ChatWsService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private nextBubbleId = 0;
  private turnIdleTimer: ReturnType<typeof setTimeout> | null = null;
  /** Bubble id receiving streamed token_delta for the pending turn. */
  private streamingBubbleId: string | null = null;

  protected readonly brandName = BRAND_NAME;
  protected readonly composerPlaceholder = COMPOSER_PLACEHOLDER;
  protected readonly sendLabel = SEND_LABEL;
  protected readonly retryLabel = RETRY_LABEL;
  protected readonly chromeReadySbRef = CHROME_READY_SB_REF;
  protected readonly chromeWorkbookRef = CHROME_WORKBOOK_REF;

  protected readonly draft = signal('');
  protected readonly bubbles = signal<ChatBubble[]>([]);
  protected readonly ctas = signal<CtaChip[]>([]);
  protected readonly inFlight = signal(false);
  /** Client turn_id of the send waiting on a terminal event; null when idle. */
  private pendingTurnId: string | null = null;
  protected readonly localError = signal<string | null>(null);
  /** Connection banner copy (network-fail or singleton conflict); null when clear. */
  protected readonly connectionBanner = signal<string | null>(null);

  protected readonly connectionState = this.ws.connectionState;

  constructor() {
    this.destroyRef.onDestroy(() => this.clearTurnIdleWatchdog());
    effect(() => {
      const state = this.connectionState();
      if (state === 'failed') {
        this.clearInFlightAndShowBanner(NETWORK_FAIL);
      } else if (state === 'conflict') {
        this.clearInFlightAndShowBanner(WS_ALREADY_OPEN);
      }
    });
  }

  ngOnInit(): void {
    this.ws.events$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((event) => {
      this.onServerEvent(event);
    });
    this.ws.undeliverable$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.onUndeliverableFrame();
    });
    this.ws.connect();
  }

  protected get composerDisabled(): boolean {
    return this.inFlight() || this.connectionBanner() !== null || this.connectionState() !== 'open';
  }

  protected onSubmit(event: Event): void {
    event.preventDefault();
    this.send();
  }

  protected onCtaClick(cta: CtaChip): void {
    if (this.composerDisabled) {
      return;
    }
    if (cta.id === 'cefr') {
      void this.router.navigateByUrl('/cefr');
      return;
    }
    const intent = CTA_INTENT[cta.id as Exclude<CtaId, 'cefr'>];
    this.sendText(intent, { showOutbound: false });
  }

  /** Minimal unit chrome — Ready SB / Workbook / clear (criterion 6 Verify). */
  protected setUnitChrome(unitRef: string | null): void {
    if (this.composerDisabled) {
      return;
    }
    this.localError.set(null);
    this.sendText('tutor_unit', {
      showOutbound: false,
      unitRef,
      includeUnitRef: true,
    });
  }

  protected send(): void {
    if (this.composerDisabled) {
      return;
    }

    const raw = this.draft();
    if (raw.length > MAX_MESSAGE_LENGTH) {
      this.localError.set(PASTE_TOO_LONG);
      return;
    }

    const text = raw.trim();
    this.localError.set(null);
    this.sendText(text, { showOutbound: text.length > 0, clearDraft: true });
  }

  private sendText(
    text: string,
    options: {
      showOutbound: boolean;
      clearDraft?: boolean;
      unitRef?: string | null;
      includeUnitRef?: boolean;
    },
  ): void {
    if (this.composerDisabled) {
      return;
    }

    const turnId = crypto.randomUUID();
    const sent = this.ws.sendTurn(
      text,
      turnId,
      options.includeUnitRef ? { unitRef: options.unitRef ?? null } : undefined,
    );
    if (!sent) {
      this.clearInFlightAndShowBanner(NETWORK_FAIL);
      return;
    }

    if (options.clearDraft) {
      this.draft.set('');
    }
    if (options.showOutbound && text.length > 0) {
      this.appendBubble({ role: 'outbound', text });
    }
    this.pendingTurnId = turnId;
    this.streamingBubbleId = null;
    this.inFlight.set(true);
    this.armTurnIdleWatchdog();
    this.ctas.set([]);
  }

  protected retryConnection(): void {
    this.connectionBanner.set(null);
    this.localError.set(null);
    this.clearPendingTurn();
    this.ws.retry();
  }

  private onServerEvent(event: ServerEvent): void {
    // Connection banner (outage or singleton conflict): ignore further frames until retry.
    if (this.connectionBanner() !== null) {
      return;
    }

    if (event.kind === 'token_delta') {
      // Only stream while a turn is awaiting a terminal event.
      if (this.pendingTurnId === null) {
        return;
      }
      if (this.isForeignTerminal(event.turn_id, { softMatchNull: true })) {
        return;
      }
      this.appendTokenDelta(event.text);
      return;
    }

    if (event.kind === 'turn_complete') {
      if (this.isForeignTerminal(event.turn_id)) {
        return;
      }
      const alreadyStreamed = this.streamingBubbleId !== null;
      this.clearPendingTurn();
      // Server message as-is; skip duplicate if token_delta already filled the bubble.
      if (!alreadyStreamed) {
        this.appendBubble({ role: 'inbound', text: event.message });
      }
      if (event.backup_notice) {
        this.appendBubble({ role: 'notice', text: event.backup_notice });
      }
      const chips = mapCtaIds(event.ctas);
      // Non-empty server list mapping to zero chips is contract drift — not silent success.
      if (event.ctas.length > 0 && chips.length === 0) {
        this.appendBubble({ role: 'system', text: UNPARSEABLE_FRAME });
        this.ctas.set([]);
        return;
      }
      this.ctas.set(chips);
      return;
    }

    if (event.kind === 'error') {
      if (this.isForeignTerminal(event.turn_id, { softMatchNull: true })) {
        return;
      }
      this.clearPendingTurn();
      this.appendBubble({ role: 'system', text: event.message });
      this.ctas.set([]);
    }
  }

  /**
   * True when a pending send exists and this terminal's turn_id is not that pending id.
   * With softMatchNull, null/undefined (omitted) matches the pending turn; empty string does not.
   */
  private isForeignTerminal(
    turnId: string | null | undefined,
    options?: { softMatchNull?: boolean },
  ): boolean {
    if (this.pendingTurnId === null) {
      return false;
    }
    if (turnId === this.pendingTurnId) {
      return false;
    }
    if (options?.softMatchNull && turnId == null) {
      return false;
    }
    return true;
  }

  private clearPendingTurn(): void {
    this.clearTurnIdleWatchdog();
    this.pendingTurnId = null;
    this.streamingBubbleId = null;
    this.inFlight.set(false);
  }

  private armTurnIdleWatchdog(): void {
    this.clearTurnIdleWatchdog();
    this.turnIdleTimer = setTimeout(() => {
      this.turnIdleTimer = null;
      this.clearInFlightAndShowBanner(NETWORK_FAIL);
    }, TURN_IDLE_MS);
  }

  private clearTurnIdleWatchdog(): void {
    if (this.turnIdleTimer !== null) {
      clearTimeout(this.turnIdleTimer);
      this.turnIdleTimer = null;
    }
  }

  /** Recover from dropped/malformed frames only while a turn is waiting on a terminal event. */
  private onUndeliverableFrame(): void {
    if (!this.inFlight()) {
      return;
    }
    this.clearPendingTurn();
    this.appendBubble({ role: 'system', text: UNPARSEABLE_FRAME });
    this.ctas.set([]);
  }

  private clearInFlightAndShowBanner(message: string): void {
    this.clearPendingTurn();
    this.connectionBanner.set(message);
  }

  private appendTokenDelta(text: string): void {
    if (this.streamingBubbleId === null) {
      const id = `b-${this.nextBubbleId++}`;
      this.streamingBubbleId = id;
      this.bubbles.update((list) => [...list, { id, role: 'inbound', text }]);
      return;
    }
    const targetId = this.streamingBubbleId;
    this.bubbles.update((list) =>
      list.map((bubble) =>
        bubble.id === targetId ? { ...bubble, text: bubble.text + text } : bubble,
      ),
    );
  }

  private appendBubble(partial: Omit<ChatBubble, 'id'>): void {
    const id = `b-${this.nextBubbleId++}`;
    this.bubbles.update((list) => [...list, { id, ...partial }]);
  }
}
