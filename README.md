# lingua.ai — Compose stack skeleton

Local modular-monolith stack: Angular `web` (Russian text-chat shell on Soft Sage tokens — chat surface T0–T1 only; **not** FR-15 / SM-8 complete), FastAPI `api`, Postgres+pgvector `db`, and an optional `ingest` Marker CPU spike job.

## Prerequisites

- Docker Compose V2
- A `.env` file (see below)

## Setup

```bash
cp .env.example .env
# Fill placeholders as needed (see Secrets checklist). Never commit .env.
```

Host publish ports are fixed in `compose.yaml` (`127.0.0.1` only): `4200` → web, `8000` → api, `5432` → db. They are not env-overridable. The web container nginx must also **listen on 4200** (not 80) so that mapping stays valid.

### Secrets checklist

Second-operator / SM-2 onboarding: copy `.env.example` → `.env`, then fill the keys below. Compose substitutes `${VAR}` from the project `.env` only — services do **not** get an `env_file` dump of every key. Never commit `.env` or real keys.

| Variable            | Required?                                                   | Purpose                                                   | How to obtain                                                                           |
| ------------------- | ----------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `POSTGRES_USER`     | **Yes** (compose fails without it)                          | Postgres role for `db` + credential parts for `api` URL   | Choose a local username (example uses `lingua`)                                         |
| `POSTGRES_PASSWORD` | **Yes**                                                     | Postgres password (raw secret for api URL construction)   | Choose a local password; keep it out of git                                             |
| `POSTGRES_DB`       | **Yes**                                                     | Database name                                             | Choose a local name (example uses `lingua`)                                             |
| `DEEPSEEK_API_KEY`  | Optional for `compose up`; needed for non-blank `/ws` turns | In-process LLM adapter (DeepSeek)                         | Create an API key at [platform.deepseek.com](https://platform.deepseek.com/) → API keys |
| `GH_TOKEN`          | No (Compose ignores it)                                     | Host GitHub CLI / Codespaces only                         | Optional; leave empty for Compose                                                       |

`DATABASE_URL` is **not** a host secret — Compose passes `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST` (`db` on the default stack, `127.0.0.1` on `compose.dev.yaml`) into `api`, which builds a percent-encoded `postgresql://` URL so passwords with `@`, `:`, `/`, etc. still parse. CI and local tests may set an explicit `DATABASE_URL` instead.

### Wipe / reset (second deploy / SM-2 isolation)

Use this when a second validation pass must not continue prior learner LTM/STM (FR-16 wipe scope). Wipe clears **everything in the Compose Postgres volume** `db_data`: learner LTM (`LearnerProfile` / CEFR, `VocabularyItem` + FSRS, `ReviewRecord`, `ErrorLog`), the non-authoritative `session` mirror, LangGraph checkpointer STM tables, and any future corpus/Ready rows in that DB.

**Does not clear:** host `.env` / secrets, or personal textbook PDFs under gitignored `textbooks/` (remove those yourself if needed). Prefer removing **only** `db_data` — do not use bare `docker compose down -v` unless you also intend to drop other named volumes (e.g. `web_dev_node_modules`).

```bash
# Pick once — SAME compose file you used to start — then reuse for every step:
dc=(docker compose)                         # default compose.yaml
# dc=(docker compose -f compose.dev.yaml)   # host-network stack instead

# 1) Stop the stack
"${dc[@]}" down

# 2) Remove only the Postgres data volume (<project>_db_data).
# Derive the name with the SAME dc; soft-fail if already absent:
DB_VOL="$("${dc[@]}" config --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['name']+'_db_data')")"
docker volume rm "$DB_VOL" 2>/dev/null || echo "No $DB_VOL volume (already clean)"

# 3) Bring the stack back up (bootstrap recreates LTM + checkpointer schemas)
"${dc[@]}" up --build
# host-network builds often need: DOCKER_BUILDKIT=0 "${dc[@]}" up --build

# 4) Confirm api is ready after bootstrap (DB probe)
curl -s http://127.0.0.1:8000/ready   # expect: {"status":"ok"}
```

After wipe: re-set CEFR via `PUT /profile/cefr` (see **LearnerProfile CEFR** below for URL, body shape, and `curl` examples) before any Ready Tutor gate; re-run ingest when that pipeline exists (stub today — see Ingest job stub). Ready Tutor requires re-ingest + CEFR re-set once those features land. When Tutor gating exists, overall CEFR must be set first (empty/missing `overall` blocks Ready Tutor — FR-7).

Personal textbook PDFs for a second machine belong under gitignored `textbooks/` at the repo root (owner must not redistribute course PDFs). Exact ingest filenames land with the ingest epic; without PDFs, SM-2 may still proceed on non-Tutor paths when those are available.

## Start the skeleton

```bash
docker compose up --build
```

Default `up` starts `web`, `api`, and `db`. The `ingest` service is **not** started (Compose profile `ingest`).

In a nested Docker / Dev Container environment, if Compose DNS cannot resolve service names (`api`, `db`), use the host-network stack instead (binds `127.0.0.1` only; no `ports:`). Prefer the classic builder so Bake does not block host networking:

```bash
docker compose down
DOCKER_BUILDKIT=0 docker compose -f compose.dev.yaml up --build
```

Ingest / web-dev with that file: `docker compose -f compose.dev.yaml --profile ingest run --rm ingest` (and the same `-f` for `--profile web-dev`).

If image builds fail to resolve PyPI/npm (common in nested Docker without iptables/NAT), rebuild with the classic builder so Compose `build.network: host` works:

```bash
DOCKER_BUILDKIT=0 docker compose up --build
```

The web Dockerfile may keep `# syntax=docker/dockerfile:1` (BuildKit); that is fine when BuildKit works. Use `DOCKER_BUILDKIT=0` only as the fallback above.

### URLs

| Service                              | URL                              |
| ------------------------------------ | -------------------------------- |
| Web (Angular chat shell via nginx)   | http://127.0.0.1:4200/           |
| API liveness (direct)                | http://127.0.0.1:8000/health     |
| API readiness (DB probe)             | http://127.0.0.1:8000/ready      |
| API readiness via web proxy          | http://127.0.0.1:4200/api/ready  |
| API learner WebSocket (via web proxy) | ws://127.0.0.1:4200/ws          |
| API learner WebSocket (direct)        | ws://127.0.0.1:8000/ws          |

Production `web` nginx proxies `/api/*` → `api:8000/*` (prefix stripped) and upgrades `/ws` → `api:8000/ws`. The chat client opens same-origin `ws[s]://{host}/ws` (scheme from the page). The `web-dev` profile / host `npm start` (`ng serve`) proxies `/ws` to `127.0.0.1:8000` via `apps/web/proxy.conf.json`; there is still no `/api/` proxy under `ng serve` — call `:8000` directly for HTTP.

Default Compose `web` serves a **production** static build (nginx). Source edits under `apps/web` (chat shell, `src/styles/tokens.css`, self-hosted fonts) are not visible until you **rebuild** the `web` image (`docker compose build web`).

For Angular HMR against the same localhost port:

```bash
docker compose stop web
docker compose --profile web-dev up web-dev
```

Or on the host: `cd apps/web && npm start` (port 4200). Do not run `web` and `web-dev` together — they both publish `127.0.0.1:4200`.

### API startup bootstrap (memory plane)

On startup the `api` prepares the shared Postgres itself — no separate migration CLI. In one critical section (FastAPI lifespan, `app/db/bootstrap.py`):

1. acquire Postgres advisory lock `7265300117001` (session-level, polled; waits at most **60 s**; connect uses a **10 s** TCP timeout and keepalives so the lock session stays up while Alembic uses a separate connection)
2. `alembic upgrade head` — learner LTM (`LearnerProfile`, `VocabularyItem` incl. FSRS fields, `ReviewRecord`, `ErrorLog`) plus the `session` mirror table (loud fail if the step exceeds **120 s**; lock still held until that in-flight work finishes)
3. `AsyncPostgresSaver.setup()` — LangGraph checkpointer tables (library-owned; never in Alembic; same **120 s** loud-fail bound; lock held through drain)
4. release the lock — after both steps have returned (or after the timed-out step’s worker finishes when step 2 fails the bound and step 3 never starts). A work timeout fails startup loudly without abandoning in-flight work; a hung worker pins the lock until the process or session dies

Uvicorn binds the port only after lifespan startup succeeds, so **`GET /health` (liveness) and `GET /ready` (readiness) are reachable only after steps 2 and 3 both succeed.** `/health` stays `200 {"status":"ok"}` while the process is up; `/ready` runs a cheap DB probe and returns `503` if Postgres is unreachable after bootstrap (Compose api healthchecks use `/ready`). Compose `api` `healthcheck.start_period` must cover the worst-case bootstrap budget before `/ready` can succeed: **lock wait (60 s) + both work bounds (120 s × 2) + margin (60 s) = 360 s** in both `compose.yaml` and `compose.dev.yaml` (CI file-asserts this against `LOCK_TIMEOUT_SECONDS` / `WORK_TIMEOUT_SECONDS`). If the health window is too short, Compose marks api unhealthy while bootstrap may still be running, which blocks `web` (`depends_on: condition: service_healthy`). A process restart (manual or via a restart policy) re-runs the whole sequence (both steps are idempotent), which also recovers a half-finished bootstrap (e.g. migrated but checkpointer missing). If DB config is missing (no explicit `DATABASE_URL` and incomplete `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `POSTGRES_HOST`), Postgres is unreachable, the lock wait times out, migrate/setup exceeds its bound, or either step fails, the process exits non-zero with a clear error and never serves.

**Single-writer MVP:** one `api` replica is the migrator. The advisory lock serializes concurrent starts (the second waits, then re-runs the idempotent sequence), but multi-replica migration orchestration is out of scope. Alembic downgrade is out of scope. The same **one replica / one uvicorn worker** pin also protects learner `/ws` occupancy (process-local `_ws_occupied`) — do not add `--workers`, `WEB_CONCURRENCY`, or `deploy.replicas` > 1; CI file-asserts on `apps/api/Dockerfile` and both Compose `api` services reject those signals.

**Stuck lock / live or dead holder:** advisory locks are released when the holding Postgres session ends, so a crashed api frees the lock. A live holder may still be draining a timed-out migrate/setup worker (peers wait up to the lock-wait bound, then see lock timeout). If a second api times out waiting, check for a live holder (`SELECT pid, state, query FROM pg_stat_activity WHERE pid IN (SELECT pid FROM pg_locks WHERE locktype='advisory');`), then restart the failed api once the holder exits or is terminated.

**Short-term memory source of truth:** the LangGraph checkpointer (`AsyncPostgresSaver`) is the STM SoT. The `Session` table (`session`) is a **non-authoritative mirror** — it is **not the source of truth** for STM, must never be read or written as if it were, and the checkpointer wins on any disagreement (AD-3, AD-9). After each successful Router checkpointer snapshot, a best-effort writer upserts one Session row for the MVP learner (`active_agent=Router`); mirror write failures are logged and must not fail the turn.

### LearnerProfile CEFR (api write path)

Sole LTM writer for CEFR is this api profile path (AD-4) — ingest and domain agents must not invent CEFR. MVP identity is one hardcoded local learner (`MVP_LEARNER_ID` in `apps/api/app/db/constants.py`); routes use singleton URLs with **no path id** (AD-10).

| Method | Path            | Behavior                                                                                                                                      |
| ------ | --------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `PUT`  | `/profile/cefr` | Full-replace `learner_profile.cefr_by_skill` for the MVP learner (other columns untouched). Body = bare CEFR map. Success → `204` No Content. |
| `GET`  | `/profile/cefr` | Bare CEFR map. No row yet → `200` `{}` and **no insert**.                                                                                     |

**Body / stored shape:** keys allowed — `overall` plus optional `reading`, `listening`, `speaking`, `writing`, `vocab`. Levels — closed set `A1\|A2\|B1\|B2\|C1\|C2` only. Unknown keys or invalid tokens → `422`, DB unchanged. `PUT` is a full replace of the JSONB column (omitted skills/`vocab` are absent after write). Omit `overall` or send `overall: null` to clear it.

**Empty overall gate signal:** missing/null `overall` after a successful write (or before any write) remains detectable — there is no silent seed/default CEFR. Later Ready Tutor gating (FR-7) will treat empty/invalid overall as block; this story only exposes the readable store.

```bash
# Example (api on :8000 after Compose up)
curl -s -X PUT http://127.0.0.1:8000/profile/cefr \
  -H 'Content-Type: application/json' \
  -d '{"overall":"B1","reading":"B1","vocab":"A2"}'
curl -s http://127.0.0.1:8000/profile/cefr
```

Tests (via **uv**, not pip): `cd apps/api && uv sync --extra dev && DATABASE_URL=postgresql://… uv run pytest -m integration_db` (needs the Compose `db`; each test uses a throwaway database on that server). Without a reachable `DATABASE_URL`, `integration_db` tests are **skipped** locally (the skip reason says they are not verified); under `CI=true` a missing/unreachable DB **fails** the run. Plain `uv run pytest` still runs `/health` and `/ready` (lifespan + mocked bootstrap; readiness DB probe mocked), mocked WebSocket/LLM turn tests, and the no-DB contract tests (missing URL, Session wording, Alembic≠checkpointer metadata).

### Learner WebSocket turns (Router skeleton)

Single unauthenticated MVP entry: **`GET /ws`** (WebSocket upgrade). All learner turns are Router turns (AD-6). At most one active `/ws` for the MVP learner — a second concurrent client is accepted briefly, then rejected with AD-6 `error` `ws_already_open` and WebSocket close code **4009** (browsers never see HTTP upgrade status); the first connection stays open and keeps occupancy. Occupancy is **process-local**, so Compose/`apps/api/Dockerfile` must keep a single api worker/replica (see Single-writer MVP above); multi-worker or multi-replica layouts are unsupported and fail the single-worker gate test. Within one connection, at most one in-flight turn (overlapping `turn_request` → `error` `invalid_turn_request`).

**Event kinds (closed set):**

| Direction       | Kind            | Role                                                                     |
| --------------- | --------------- | ------------------------------------------------------------------------ |
| client → server | `turn_request`  | `{ "kind": "turn_request", "text": "<string>", "turn_id"?: "<string>" }` |
| server → client | `token_delta`   | Streaming tokens (unused on CTA/blank skeleton paths)                    |
| server → client | `turn_complete` | End of turn; CTA/clarify payloads live here                              |
| server → client | `error`         | Structured failure                                                       |

Optional client `turn_id` is echoed on the matching `turn_complete` / `error`; omit it when the request had none.

**CTA / blank skeleton (this story):** no domain agent nodes and no free-form chat. Non-blank turns call the in-process DeepSeek adapter (classify stub); with no handoff, the reply is a fixed Russian template `message`, `ctas: ["tutor","vocabulary","review"]`, `clarify: null`, and `backup_notice` (string or null). Blank / whitespace-only `text` (after Unicode strip) returns the same CTA shape **without** calling the LLM. Zero `token_delta` on these paths. Adapter completion text is never copied into `message`.

**LLM degrade (FR-1 subset):** primary `deepseek-flash`, escalation `deepseek-v4-pro` (OpenAI-compatible `https://api.deepseek.com`). Compose passes `DEEPSEEK_API_KEY` into `api` from `.env`. Missing/empty key → `error` `llm_misconfigured`. Both models down / unreachable / timeout / incomplete → `error` `llm_unavailable`. Escalation success → `backup_notice`: `Сейчас отвечает запасная модель.` (never folded into `message`). No monthly spend-cap enforcement in this story; per-request timeout and `max_tokens` still apply. No invented chat content.

**Error `code` values:** `llm_misconfigured` | `llm_unavailable` | `invalid_turn_request` | `checkpointer_write_failed` | `ws_already_open`. Invalid inbound (non-JSON, bad kind, missing/non-string `text`, or `text` longer than 2000 characters) and overlapping in-flight turns use `invalid_turn_request` with no LLM call and no checkpointer write. Checkpointer snapshot write happens only after successful CTA/blank handling (Router sole writer, AD-3); failed `aput` → `checkpointer_write_failed` and no success `turn_complete`. Singleton conflict (`ws_already_open`) is sent on a briefly accepted second `/ws` before close `4009`.

```bash
# Example (api on :8000; needs websocat or similar)
# Blank → CTA without LLM:
printf '%s\n' '{"kind":"turn_request","text":"  ","turn_id":"1"}' | websocat -n ws://127.0.0.1:8000/ws
# Non-blank with key set → CTA (or error if LLM down / key unset)
```

### Quality gates

Local commands (no Docker required for lint/format/typecheck). Api uses **uv** against `apps/api/uv.lock`; web uses npm.

**Api** (`apps/api`):

```bash
cd apps/api
uv sync --extra dev
uv run ruff check app
uv run ruff format --check app
uv run mypy
```

**Web** (`apps/web`):

```bash
cd apps/web
npm ci
npm run lint
npm run format:check
npm run typecheck
npm test   # ng test --watch=false (Vitest + jsdom; not e2e)
```

**CI** (`.github/workflows/ci.yml` on push/PR to `main`): api ruff + mypy; api `uv run pytest -m "not integration_db"` (no Postgres); api `uv run pytest -m integration_db` against a `pgvector/pgvector:pg16` service with `DATABASE_URL` and `CI=true` (skipped `integration_db` is a failure); web lint / format check / typecheck; web unit tests with `--watch=false`.

### Ingest Marker CPU spike

Startable without `db` (Compose profile `ingest`). Mounts gitignored `textbooks/` read-only and prints one JSON metrics object per Students’ Book / Workbook PDF (`status` `ok` | `fallback` | `parse_failed`). Image ships pinned CPU `llama-server` for Marker/Surya. Missing required PDF → non-zero exit + path on stderr. Does **not** mint Ready units or write the spike note — owner HITL fills `_bmad-output/.../spike-marker-compose-cpu-spike-note.md`.

```bash
docker compose --profile ingest run --rm ingest
# nested Docker:
docker compose -f compose.dev.yaml --profile ingest run --rm ingest
```

## Layout

```text
compose.yaml       # default bridge topology (service DNS + ports)
compose.dev.yaml   # nested-Docker host-network alternative
apps/
  api/      # FastAPI + /health + /ready + /profile/cefr + /ws Router turns, LLM adapter, bootstrap, LTM
  web/      # Angular 22.2.x chat shell + Soft Sage tokens (T0–T1; + nginx.dev.conf for host stack)
  ingest/   # Marker Compose CPU spike job (profile ingest)
```
