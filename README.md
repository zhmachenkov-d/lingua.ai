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

Host publish ports are fixed in `compose.yaml` (`127.0.0.1` only): `4200` → web, `8000` → api, `5432` → db. They are not env-overridable.

## Start the skeleton

```bash
# Nested/devcontainer Docker without iptables/NAT: use classic builder so
# compose `build.network: host` can reach PyPI/npm during image builds.
DOCKER_BUILDKIT=0 docker compose up --build
```

Default `up` starts `web`, `api`, and `db`. The `ingest` service is **not** started (Compose profile `ingest`).

### URLs

| Service | URL |
| ------- | --- |
| Web (Angular default shell) | http://127.0.0.1:4200/ |
| API health | http://127.0.0.1:8000/health |

### Ingest job stub

Startable without `db`. Logs one start line and exits 0 (no Ready pipeline yet):

```bash
docker compose --profile ingest run --rm ingest
```

## Layout

```text
compose.yaml
apps/
  api/      # FastAPI + GET /health
  web/      # Angular 22.2.x default shell
  ingest/   # job-profile stub
```
