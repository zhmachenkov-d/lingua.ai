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
  api/      # FastAPI + GET /health
  web/      # Angular 22.2.x default shell (+ nginx.dev.conf for host stack)
  ingest/   # job-profile stub
```
