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
  | 'ws_already_open'
  | (string & {});

/** Application close code for singleton /ws conflict (mirrors historical HTTP 409). */
export const WS_ALREADY_OPEN_CLOSE_CODE = 4009;

export interface TurnRequest {
  kind: TurnRequestKind;
  text: string;
  turn_id?: string;
  /** Present (incl. null clear) is chrome; omit = no unit change. */
  unit_ref?: string | null;
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

export type CtaId = 'tutor' | 'vocabulary' | 'review' | 'cefr' | 'confirm_unit' | 'decline_unit';

export interface CtaChip {
  id: CtaId;
  label: string;
}
