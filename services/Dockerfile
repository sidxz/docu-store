# docu-store backend — single image, multiple entrypoints
#
# Default CMD runs the FastAPI API server.
# Workers override CMD in docker-compose:
#   read-worker:      .venv/bin/python -m infrastructure.read_worker
#   pipeline-worker:  .venv/bin/python -m infrastructure.pipeline_worker
#   temporal-worker:  .venv/bin/python -m infrastructure.temporal.worker
#   llm-worker:       .venv/bin/python -m infrastructure.temporal.llm_worker
#   plugin-consumer:  .venv/bin/python -m infrastructure.plugins.plugin_consumer

FROM python:3.12-slim

# System deps: librdkafka for confluent-kafka, poppler for pdf2image, wget for healthcheck,
# libgl1-mesa-glx + libglib2.0-0 for opencv (required by DECIMER/OCSR)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      librdkafka-dev \
      poppler-utils \
      wget \
      libgl1 \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Deps layer — only re-runs when actual dependencies change (not version bumps)
COPY uv.lock ./
COPY pyproject.toml ./tmp_pyproject.toml
RUN sed '/^version *=/d' ./tmp_pyproject.toml > ./pyproject.toml && rm ./tmp_pyproject.toml
RUN uv sync --no-dev --no-install-project --frozen

# Restore real pyproject.toml (with version) + application code
COPY pyproject.toml ./
COPY application/ application/
COPY domain/ domain/
COPY infrastructure/ infrastructure/
COPY interfaces/ interfaces/

# Non-root user (UID 1000 — standard for k8s SecurityContext)
RUN useradd -r -u 1000 -m docustore
USER docustore

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD wget -qO- http://localhost:8000/health || exit 1

CMD [".venv/bin/uvicorn", "interfaces.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
