# Web — Lingua AI chat shell

Angular 22 learner UI under `apps/web`. This story ships a **Russian-chrome text-chat shell** (thread + composer + disabled Router CTA row) wired to the api WebSocket at same-origin `/ws` (`ws`/`wss` from the page), with Soft Sage `--lingua-*` tokens on the **primary chat surface only** (FR-15 **T0–T1** chat slice).

**Not claimed:** full FR-15 / SM-8 (Tutor / Vocabulary / Review claim surfaces, theme toggle chrome, empty/refuse checklist beyond chat network-fail / paste-too-long).

## Local URLs

| Surface                                                    | URL                                              |
| ---------------------------------------------------------- | ------------------------------------------------ |
| Chat UI                                                    | http://127.0.0.1:4200/                           |
| Learner WebSocket (same-origin via nginx/`ng serve` proxy) | `ws://{host}/ws` (e.g. `ws://127.0.0.1:4200/ws`) |

Compose production `web` nginx proxies `/api/` and upgrades `/ws`. Host/`web-dev` `ng serve` uses `proxy.conf.json` for `/ws` → `127.0.0.1:8000`.

## Design tokens

- Token file: `src/styles/tokens.css` (imported from `src/styles.css`)
- Theme: default `data-theme="light"` on `<html>`; dark overrides the same `--lingua-*` names (`data-theme="dark"` — DevTools spot-check; toggle deferred)
- Fonts: self-hosted Literata + Source Sans 3 under `public/fonts/` (Compose offline-friendly; no CDN)

## Development

```bash
npm ci
npm start          # ng serve → :4200
```

Quality gates:

```bash
npm run lint
npm run format:check
npm run typecheck
npm test           # ng test --watch=false
```

## Compose

Default Compose `web` serves a **production** static build. After changing this app, rebuild the image:

```bash
docker compose build web && docker compose up
```

Or use the `web-dev` profile / host `npm start` for HMR (see root README).
