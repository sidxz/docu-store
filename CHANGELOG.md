# Changelog

Changes to the API, workers and web portal. The CLI keeps its own log in [cli/CHANGELOG.md](cli/CHANGELOG.md).

## [Unreleased]

### Added
- The API publishes the release's bundled prompts to Langfuse when it starts, in the background. A new Langfuse version is created only when a bundled prompt changed, so restarts add nothing. It uses the existing `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. When upgrading, remove any step that seeds prompts into Langfuse from outside: a version written from outside after the app's own counts as an edit and stays in use.
- A prompt edited in the Langfuse UI stays in use until a release ships a changed version of that same prompt. The release's version then takes over, and the edit stays in the prompt's history. The version the app last published carries the `bundled` label. The first start after upgrading is the exception: nothing carries the label yet, so a prompt whose current Langfuse version differs from the bundled one is replaced by the bundled one.

### Fixed
- A prompt missing from Langfuse, or an unreachable Langfuse, no longer fails the LLM call. The bundled prompt is used instead.
- Fetching a prompt no longer blocks the event loop while Langfuse is slow to answer.
- `PROMPT_REPOSITORY_TYPE=yaml` finds the bundled prompts. It looked in a folder that does not exist.

### Removed
- `make langfuse-seed` and `scripts/seed_langfuse_prompts.py`. `make docker-up` no longer seeds prompts; the API publishes them on its first start.

## [2.0.0] - 2026-11-17

Released as `services-v2.0.0` and `web-v2.0.0`.

### Added
- Per-workspace storage limits. Workspace admins set one in Settings → Storage, and `MAX_WORKSPACE_STORAGE_MB` caps every workspace on the deployment (unset means no cap). The lower of the two applies, to admins as well. An upload that would go over it is refused with HTTP 413 before anything is stored.
- Settings → Storage for workspace admins: uploaded size against the limit, disk use including page images and parsed text, and a limit editor that stops at the deployment cap.
- `GET /workspace/storage` and `PUT /workspace/storage/limit`, for workspace admins. A limit above the deployment cap returns 422.
- Documents record the size of their uploaded file (`source_size_bytes`).

### Changed
- **Breaking:** blob storage is organized by workspace. All of a document's files live under `workspaces/{workspace_id}/artifacts/{artifact_id}/`. Nothing moves existing files, so on an existing install, documents uploaded before this change lose their page images, thumbnails and other derived files until those are moved to the new paths. Start from an empty blob store, or move the files before upgrading.
- Deleting a document deletes all of its stored files.

### Fixed
- A document's original file is stored with its page images and parsed text.
- Deleting a document removes it from document lists.

### Security
- Dependencies updated past their published advisories. Services: Pillow 13.0.0 (with docling 2.142.1, the first release that supports it), pypdf 7.1.0, dnspython 2.9.2, mail-parser 4.11.0, pyasn1 0.6.5, soupsieve 4.1.1, temporalio 1.35.0, certifi 2026.10.19, filelock 4.2.1, setuptools 84.1.0 and OpenTelemetry 1.45.2. Web: Next.js 16.4.6, zod 4.6.7 and fast-uri 3.1.9.
