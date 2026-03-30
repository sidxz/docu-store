# DocuStore

Document intelligence for drug discovery. Event-sourced, AI-enriched, built to keep scientific work explainable, searchable, and ready for the next breakthrough.

[![CI](https://github.com/sidxz/docu-store/actions/workflows/tests.yml/badge.svg)](https://github.com/sidxz/docu-store/actions/workflows/tests.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)

## Architecture

```
                                    +------------------+
                                    |   Next.js 16     |
                                    |   Portal (web)   |
                                    +--------+---------+
                                             |
+----------------+    +---------+    +-------v--------+    +----------------+
| EventStoreDB   |<-->| FastAPI |<-->|   MongoDB      |    | Qdrant         |
| (event store)  |    | (API)   |    | (read models)  |    | (vectors)      |
+-------+--------+    +----+----+    +----------------+    +-------+--------+
        |                  |                                       |
        v                  v                                       |
+-------+--------+  +-----+------+                                |
| Read Worker    |  | Pipeline   |     +------------------+       |
| (projections)  |  | Worker     +---->| Temporal         +-------+
+----------------+  | (triggers) |     | CPU/LLM Workers  |
                    +-----+------+     +------------------+
                          |
                    +-----v------+
                    | Kafka      |
                    | (plugins)  |
                    +------------+
```

**Backend** (`services/`): Python, FastAPI, event sourcing (EventStoreDB), CQRS (MongoDB), Temporal workflows, Qdrant vector search, Kafka event streaming.

**Frontend** (`web/`): Next.js 16, PrimeReact, TanStack Query, pnpm monorepo.

**6 backend processes** from a single image:

| Process | Purpose |
|---------|---------|
| API | FastAPI server (port 8000) |
| Read Worker | Event projections to MongoDB |
| Pipeline Worker | Event-driven workflow triggers |
| Temporal Worker | Embeddings, compound extraction (CPU-bound) |
| LLM Worker | Summarization, NER, metadata extraction |
| Plugin Consumer | Kafka-to-Temporal plugin bridge |

## Quick Start (Development)

**Prerequisites**: Docker, Python 3.12+, uv, Node.js 22+, pnpm

```bash
# 1. Start infrastructure (Mongo, EventStoreDB, Kafka, Temporal, Qdrant, Langfuse, Umami)
cd services
make docker-up

# 2. Install backend dependencies
make dev-install

# 3. Start all backend services
make run-all

# 4. Start frontend (separate terminal)
cd web
pnpm install
pnpm dev
```

**Services**:
- API: http://localhost:8000
- Portal: http://localhost:15000
- EventStoreDB UI: http://localhost:2113
- Temporal UI: http://localhost:8233
- Kafka UI: http://localhost:5051
- Qdrant: http://localhost:6333/dashboard
- Langfuse: http://localhost:3000
- Umami: http://localhost:3001

## Docker Images

Both images are universal (config via environment variables at runtime).

| Image | Registry |
|-------|----------|
| `ghcr.io/sidxz/docu-store` | Backend (all 6 processes) |
| `ghcr.io/sidxz/docu-store-web` | Frontend (Next.js standalone) |

### Build locally

```bash
cd services && make docker-build      # backend
cd services && make docker-build-web  # frontend
```

### Publish (via GitHub Actions)

Tag pushes trigger image builds:

```bash
git tag services-v0.2.0 && git push origin services-v0.2.0  # backend
git tag web-v0.2.0 && git push origin web-v0.2.0            # frontend
```

## Deployment

### Docker Compose (standalone)

Everything needed to run DocuStore in two compose files:

```bash
# 1. Copy and fill in secrets
cp .env.prod.example .env.prod

# 2. Start infrastructure
docker compose -f docker-compose.infra.yml up -d

# 3. Start application
docker compose -f docker-compose.prod.yml up -d
```

### Docker Swarm

```bash
# 1. Create the overlay network
docker network create -d overlay docu-store

# 2. Deploy infrastructure
docker stack deploy -c docker-compose.infra.yml docu-store-infra

# 3. Deploy application
docker stack deploy -c docker-compose.prod.yml docu-store
```

### Configuration

All configuration is via environment variables. See `.env.prod.example` for the full reference.

**Backend**: reads env vars via pydantic-settings (`services/infrastructure/config.py`).

**Frontend**: reads `APP_*` env vars at runtime via `/api/config` endpoint (not baked at build time). For local dev, `NEXT_PUBLIC_*` vars in `.env.local` are used as fallback.

| Variable | Purpose |
|----------|---------|
| `EVENTSTOREDB_URI` | EventStoreDB connection |
| `MONGO_URI` | MongoDB connection (requires replica set) |
| `TEMPORAL_ADDRESS` | Temporal server address |
| `QDRANT_URL` | Qdrant vector DB URL |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address |
| `SENTINEL_URL` | Sentinel auth service URL |
| `SENTINEL_SERVICE_KEY` | Sentinel service API key |
| `LLM_PROVIDER` | LLM backend: `ollama`, `openai`, `gemini` |
| `EMBEDDING_DEVICE` | `cpu`, `cuda`, or `mps` |
| `APP_API_URL` | Frontend: API base URL (runtime) |
| `APP_SENTINEL_URL` | Frontend: Sentinel URL (runtime) |

## CI/CD

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| `tests.yml` | Push/PR to `main` | Lint (ruff), tests (pytest), Trivy container scan |
| `publish-services.yml` | `services-v*` tag | Build + push backend to GHCR |
| `publish-web.yml` | `web-v*` tag | Build + push frontend to GHCR |

All workflows use GitHub Actions Docker layer caching for fast rebuilds.

## Project Structure

```
docu-store/
├── services/                    # Backend (Python)
│   ├── domain/                  #   DDD aggregates, value objects
│   ├── application/             #   Use cases, DTOs, ports
│   ├── infrastructure/          #   Adapters, workers, Temporal, vector stores
│   ├── interfaces/api/          #   FastAPI routes
│   ├── tests/                   #   Unit + integration tests
│   ├── Dockerfile               #   Backend image
│   └── docker-compose.yml       #   Dev infrastructure
├── web/                         # Frontend (Next.js 16, pnpm monorepo)
│   ├── apps/portal/             #   Main web application
│   ├── packages/                #   Shared: api-client, types, ui, tsconfig
│   └── Dockerfile               #   Frontend image
├── docker-compose.infra.yml     # Production infrastructure
├── docker-compose.prod.yml      # Production application
└── .env.prod.example            # Production config template
```

## Further Reading

- `services/design_docs/TESTING_QUICK_REFERENCE.md` — local test setup
- `services/design_docs/WORKER_SETUP.md` — worker configuration
- `services/design_docs/SUMMARY_EMBEDDINGS_AND_SEARCH.md` — search architecture
