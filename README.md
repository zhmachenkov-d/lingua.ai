# lingua.ai — Compose stack skeleton

Local modular-monolith **stack/skeleton shell** (not the learner UI). Tracer-bullet topology: Angular `web`, FastAPI `api`, Postgres+pgvector `db`, and an optional `ingest` job stub.

## Prerequisites

- Docker Compose V2
- A `.env` file (see below)

## Setup

```bash
cp .env.example .env
# Fill placeholders as needed (DB credentials, empty LLM stubs). Never commit .env.
```

Host publish ports are fixed in `compose.yaml` (`127.0.0.1` only): `4200` → web, `8000` → api, `5432` → db. They are not env-overridable. The web container nginx must also **listen on 4200** (not 80) so that mapping stays valid.

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

| Service                                  | URL                              |
| ---------------------------------------- | -------------------------------- |
| Web (Angular production build via nginx) | http://127.0.0.1:4200/           |
| API health (direct)                      | http://127.0.0.1:8000/health     |
| API health via web proxy                 | http://127.0.0.1:4200/api/health |

Production `web` nginx proxies `/api/*` → `api:8000/*` (prefix stripped). The `web-dev` profile (`ng serve`) does not include that proxy — call `:8000` directly or use host `npm start` with a later Angular proxy config.

Default Compose `web` serves a **production** static build (nginx). Source edits under `apps/web` are not visible until you rebuild the image.

For Angular HMR against the same localhost port:

```bash
docker compose stop web
docker compose --profile web-dev up web-dev
```

Or on the host: `cd apps/web && npm start` (port 4200). Do not run `web` and `web-dev` together — they both publish `127.0.0.1:4200`.

### API startup bootstrap (memory plane)

On startup the `api` prepares the shared Postgres itself — no separate migration CLI. In one critical section (FastAPI lifespan, `app/db/bootstrap.py`):

1. acquire Postgres advisory lock `7265300117001` (session-level, polled; waits at most **60 s**; connect uses a **10 s** TCP timeout and keepalives so the lock session stays up while Alembic uses a separate connection)
2. `alembic upgrade head` — learner LTM (`LearnerProfile`, `VocabularyItem` incl. FSRS fields, `ReviewRecord`, `ErrorLog`) plus the `session` mirror table (bounded **120 s** under the lock)
3. `AsyncPostgresSaver.setup()` — LangGraph checkpointer tables (library-owned; never in Alembic; also bounded **120 s**)
4. release the lock

Uvicorn binds the port only after lifespan startup succeeds, so **`GET /health` → `200 {"status":"ok"}` is reachable only after steps 2 and 3 both succeed.** If `DATABASE_URL` is missing, Postgres is unreachable, the lock wait times out, migrate/setup exceeds its bound, or either step fails, the process exits non-zero with a clear error and never serves. A restart re-runs the whole sequence (both steps are idempotent), which also recovers a half-finished bootstrap (e.g. migrated but checkpointer missing).

**Single-writer MVP:** one `api` replica is the migrator. The advisory lock serializes concurrent starts (the second waits, then re-runs the idempotent sequence), but multi-replica migration orchestration is out of scope. Alembic downgrade is out of scope.

**Stuck lock / dead holder:** advisory locks are released when the holding Postgres session ends, so a crashed api frees the lock. If a second api times out waiting, check for a live holder (`SELECT pid, state, query FROM pg_stat_activity WHERE pid IN (SELECT pid FROM pg_locks WHERE locktype='advisory');`), then restart the failed api once the holder exits or is terminated.

**Short-term memory source of truth:** the LangGraph checkpointer (`AsyncPostgresSaver`) is the STM SoT. The `Session` table (`session`) is a **non-authoritative mirror** — it is **not the source of truth** for STM, must never be read or written as if it were, and the checkpointer wins on any disagreement (AD-3, AD-9).

Tests (via **uv**, not pip): `cd apps/api && uv sync --extra dev && DATABASE_URL=postgresql://… uv run pytest -m integration_db` (needs the Compose `db`; each test uses a throwaway database on that server). Without a reachable `DATABASE_URL`, `integration_db` tests are **skipped** locally (the skip reason says they are not verified); under `CI=true` a missing/unreachable DB **fails** the run. Plain `uv run pytest` still runs `/health` (lifespan + mocked bootstrap) and the no-DB contract tests (missing URL, Session wording, Alembic≠checkpointer metadata).

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

**CI** (`.github/workflows/ci.yml` on push/PR to `main`): api ruff + mypy; api `uv run pytest -m integration_db` against a `pgvector/pgvector:pg16` service with `DATABASE_URL` and `CI=true` (skipped `integration_db` is a failure); web lint / format check / typecheck; web unit tests with `--watch=false`.

### Ingest job stub

Startable without `db`. Logs one start line and exits 0 (no Ready pipeline yet):

```bash
docker compose --profile ingest run --rm ingest
```

## Layout

```text
compose.yaml       # default bridge topology (service DNS + ports)
compose.dev.yaml   # nested-Docker host-network alternative
apps/
  api/      # FastAPI + GET /health, startup bootstrap, LTM models + Alembic
  web/      # Angular 22.2.x default shell (+ nginx.dev.conf for host stack)
  ingest/   # job-profile stub
```
