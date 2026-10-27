# ADR: Unauthenticated singleton learner WebSocket with detectable conflict

Story 1.5 introduced the learner turn path before multi-user auth and domain agents. The plan (`story-websocket-turn-skeleton-with-llm-adapter-and-cta-plan.md`) decided on a single unauthenticated `GET /ws` upgrade for the MVP singleton learner, rejecting a second concurrent connection and allowing at most one in-flight turn per connection (commit `0dd45a5`). The why in the plan: MVP identity is one learner (`MVP_LEARNER_ID`); WS auth/origin policy and multi-user sessions are out of this story; the singleton gate makes the C2 single-socket assumption enforceable without inventing auth.

## Conflict signal (browser-detectable)

Browser WebSocket clients never expose the HTTP status of a failed upgrade, so pre-accept HTTP 409 alone is indistinguishable from a network failure in the chat UI (#68). The live contract is:

1. Leave occupancy with the holder (first open socket).
2. For a rejectee: `accept()` → send AD-6 `{"kind":"error","code":"ws_already_open",...}` → `close(code=4009)` (application range 4000–4999; 4009 mirrors the historical 409).
3. The rejected socket never claims `_ws_occupied`.
4. The first connection stays open and usable.

Clients key off the error code and/or close code `4009`. Do not rely on HTTP status. Chat chrome shows distinct RU singleton-conflict copy (not the generic network-fail banner alone); retry remains manual only.
