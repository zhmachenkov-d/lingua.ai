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
} from './chat.copy';
import { ChatWsService } from './chat-ws.service';
import { mapCtaIds } from './cta-labels';
import type { ChatBubble, CtaChip, ServerEvent } from './chat.types';

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

  protected readonly brandName = BRAND_NAME;
  protected readonly composerPlaceholder = COMPOSER_PLACEHOLDER;
  protected readonly sendLabel = SEND_LABEL;
  protected readonly soonLabel = SOON_LABEL;
  protected readonly retryLabel = RETRY_LABEL;
  protected readonly networkFail = NETWORK_FAIL;

  protected readonly draft = signal('');
  protected readonly bubbles = signal<ChatBubble[]>([]);
  protected readonly ctas = signal<CtaChip[]>([]);
  protected readonly inFlight = signal(false);
  /** Client turn_id of the send waiting on a terminal event; null when idle. */
  private pendingTurnId: string | null = null;
  protected readonly localError = signal<string | null>(null);
  protected readonly showNetworkFail = signal(false);

  protected readonly connectionState = this.ws.connectionState;

  constructor() {
    effect(() => {
      const state = this.connectionState();
      if (state === 'failed') {
        this.clearInFlightAndShowNetworkFail();
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
    return this.inFlight() || this.showNetworkFail() || this.connectionState() !== 'open';
  }

  protected onSubmit(event: Event): void {
    event.preventDefault();
    this.send();
  }

  protected send(): void {
    if (this.inFlight() || this.showNetworkFail() || this.connectionState() !== 'open') {
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
      this.clearInFlightAndShowNetworkFail();
      return;
    }

    if (text.length > 0) {
      this.appendBubble({ role: 'outbound', text });
    }
    this.draft.set('');
    this.pendingTurnId = turnId;
    this.inFlight.set(true);
    this.ctas.set([]);
  }

  protected retryConnection(): void {
    this.showNetworkFail.set(false);
    this.localError.set(null);
    this.clearPendingTurn();
    this.ws.retry();
  }

  private onServerEvent(event: ServerEvent): void {
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
      this.ctas.set(mapCtaIds(event.ctas));
      return;
    }

    if (event.kind === 'error') {
      if (this.isForeignTerminal(event.turn_id)) {
        return;
      }
      this.clearPendingTurn();
      this.appendBubble({ role: 'system', text: event.message });
      this.ctas.set([]);
    }
  }

  /** True when a pending send exists and this terminal's turn_id is not that pending id. */
  private isForeignTerminal(turnId: string | null | undefined): boolean {
    return this.pendingTurnId !== null && turnId !== this.pendingTurnId;
  }

  private clearPendingTurn(): void {
    this.pendingTurnId = null;
    this.inFlight.set(false);
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

  private clearInFlightAndShowNetworkFail(): void {
    this.clearPendingTurn();
    this.showNetworkFail.set(true);
  }

  private appendBubble(partial: Omit<ChatBubble, 'id'>): void {
    const id = `b-${this.nextBubbleId++}`;
    this.bubbles.update((list) => [...list, { id, ...partial }]);
  }
}
