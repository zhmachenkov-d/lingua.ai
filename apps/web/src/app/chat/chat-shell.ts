import { Component, DestroyRef, OnInit, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import {
  BRAND_NAME,
  COMPOSER_PLACEHOLDER,
  MAX_MESSAGE_LENGTH,
  NETWORK_FAIL,
  PASTE_TOO_LONG,
  RETRY_LABEL,
  SEND_LABEL,
  SOON_LABEL,
  UNPARSEABLE_FRAME,
  WS_ALREADY_OPEN,
} from './chat.copy';
import { ChatWsService } from './chat-ws.service';
import { mapCtaIds } from './cta-labels';
import type { ChatBubble, CtaChip, ServerEvent } from './chat.types';

/**
 * Idle ms with no matching terminal event before network-fail recovery (#60 / #111).
 * Must stay strictly above server turn wall-clock worst case:
 * 2×REQUEST_TIMEOUT_SECONDS (primary+escalate) + 2×CHECKPOINTER_WRITE_TIMEOUT_SECONDS
 * (snapshot then session-mirror) = 120s, plus a small delivery margin.
 */
export const TURN_IDLE_MS = 125_000;

@Component({
  selector: 'app-chat-shell',
  imports: [FormsModule],
  templateUrl: './chat-shell.html',
  styleUrl: './chat-shell.css',
})
export class ChatShell implements OnInit {
  private readonly ws = inject(ChatWsService);
  private readonly destroyRef = inject(DestroyRef);
  private nextBubbleId = 0;
  private turnIdleTimer: ReturnType<typeof setTimeout> | null = null;

  protected readonly brandName = BRAND_NAME;
  protected readonly composerPlaceholder = COMPOSER_PLACEHOLDER;
  protected readonly sendLabel = SEND_LABEL;
  protected readonly soonLabel = SOON_LABEL;
  protected readonly retryLabel = RETRY_LABEL;

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

  protected send(): void {
    if (this.inFlight() || this.connectionBanner() !== null || this.connectionState() !== 'open') {
      return;
    }

    const raw = this.draft();
    if (raw.length > MAX_MESSAGE_LENGTH) {
      this.localError.set(PASTE_TOO_LONG);
      return;
    }

    const text = raw.trim();
    this.localError.set(null);

    const turnId = crypto.randomUUID();
    const sent = this.ws.sendTurn(text, turnId);
    if (!sent) {
      this.clearInFlightAndShowBanner(NETWORK_FAIL);
      return;
    }

    if (text.length > 0) {
      this.appendBubble({ role: 'outbound', text });
    }
    this.draft.set('');
    this.pendingTurnId = turnId;
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
      // Parsed and ignored — no streaming UI this story.
      return;
    }

    if (event.kind === 'turn_complete') {
      if (this.isForeignTerminal(event.turn_id)) {
        return;
      }
      this.clearPendingTurn();
      // Server message as-is (including blank → server CTA_MESSAGE; no client rewrite).
      this.appendBubble({ role: 'inbound', text: event.message });
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

  private appendBubble(partial: Omit<ChatBubble, 'id'>): void {
    const id = `b-${this.nextBubbleId++}`;
    this.bubbles.update((list) => [...list, { id, ...partial }]);
  }
}
