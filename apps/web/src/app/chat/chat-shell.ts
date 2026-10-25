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
    this.inFlight.set(true);
    this.ctas.set([]);
  }

  protected retryConnection(): void {
    this.showNetworkFail.set(false);
    this.localError.set(null);
    this.inFlight.set(false);
    this.ws.retry();
  }

  private onServerEvent(event: ServerEvent): void {
    if (event.kind === 'token_delta') {
      // Parsed and ignored — no streaming UI this story.
      return;
    }

    if (event.kind === 'turn_complete') {
      this.inFlight.set(false);
      // Server message as-is (including blank → server CTA_MESSAGE; no client rewrite).
      this.appendBubble({ role: 'inbound', text: event.message });
      if (event.backup_notice) {
        this.appendBubble({ role: 'notice', text: event.backup_notice });
      }
      this.ctas.set(mapCtaIds(event.ctas));
      return;
    }

    if (event.kind === 'error') {
      this.inFlight.set(false);
      this.appendBubble({ role: 'system', text: event.message });
      this.ctas.set([]);
    }
  }

  private clearInFlightAndShowNetworkFail(): void {
    this.inFlight.set(false);
    this.showNetworkFail.set(true);
  }

  private appendBubble(partial: Omit<ChatBubble, 'id'>): void {
    const id = `b-${this.nextBubbleId++}`;
    this.bubbles.update((list) => [...list, { id, ...partial }]);
  }
}
