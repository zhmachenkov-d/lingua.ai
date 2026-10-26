/**
 * AD-6 WebSocket envelopes — shapes align with apps/api/app/schemas/ws.py.
 * Client `ErrorCode` accepts unknown wire strings so contract drift cannot stick in-flight;
 * the api schema remains a closed Literal.
 */

export type TurnRequestKind = 'turn_request';

export type ErrorCode =
  | 'llm_misconfigured'
  | 'llm_unavailable'
  | 'invalid_turn_request'
  | 'checkpointer_write_failed'
  | (string & {});

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
