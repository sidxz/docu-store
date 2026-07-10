---
name: verify
description: How to verify backend (services/) changes at runtime in this repo
---

# Verifying docu-store backend changes

- Tests: `cd services && uv run pytest tests/ -q` (~25s, no external deps needed).
- No local docker stack for docu-store runs on this machine (other projects' containers do run — don't confuse them). Full API/worker verification needs `make docker-up` in `services/` (heavy) or the prod stack on ned.
- Driving infra components directly: write a script in the scratchpad, run with `cd services && PYTHONPATH=$PWD uv run python <script>`. Real dev-uploaded PDFs live in `services/blobs/artifacts/*/source.pdf` (smallest ~20KB: `ae354183-…`). Build `FsspecBlobStore(base_url=settings.blob_base_url, storage_options=getattr(settings, "blob_storage_options", None))` — matches container wiring.
- Gotcha: anything using multiprocessing spawn (e.g. `SubprocessParser`) requires the drive script to have an `if __name__ == "__main__":` guard, or the child dies at bootstrap with `exitcode=1`.
- First real docling parse loads models (~10s overhead, cached under HF cache).
- Compose validation: `.env.prod` doesn't exist locally — `touch .env.prod`, run `docker compose -f docker-compose.prod.yml config --quiet`, then `rm .env.prod`.
- Healthcheck/container-level commands can be smoke-tested in the real base image: `docker run --rm python:3.12-slim sh -c '…'`.
