/** AD-6 WebSocket envelopes — mirrors apps/api/app/schemas/ws.py. */

export type TurnRequestKind = 'turn_request';
export type ServerEventKind = 'token_delta' | 'turn_complete' | 'error';

export type ErrorCode =
  'llm_misconfigured' | 'llm_unavailable' | 'invalid_turn_request' | 'checkpointer_write_failed';

export interface TurnRequest {
  kind: TurnRequestKind;
  text: string;
  turn_id?: string;
}

export interface TurnCompleteEvent {
  kind: 'turn_complete';
  message: string;
  ctas: string[];
  clarify: null;
  backup_notice: string | null;
  turn_id?: string | null;
}

export interface ErrorEvent {
  kind: 'error';
  message: string;
  code: ErrorCode;
  turn_id?: string | null;
}

export interface TokenDeltaEvent {
  kind: 'token_delta';
  text: string;
  turn_id?: string | null;
}

export type ServerEvent = TurnCompleteEvent | ErrorEvent | TokenDeltaEvent;

export type ChatBubbleRole = 'outbound' | 'inbound' | 'system' | 'notice';

export interface ChatBubble {
  id: string;
  role: ChatBubbleRole;
  text: string;
}

export type CtaId = 'tutor' | 'vocabulary' | 'review';

export interface CtaChip {
  id: CtaId;
  label: string;
}
