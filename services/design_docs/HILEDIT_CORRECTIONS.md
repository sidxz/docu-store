# hiledit — Human-in-the-Loop Corrections for Extracted Metadata

**Status:** approved for implementation (2026-07-14)
**Motivation:** OCR/extraction errors (Docling parse, CSER compound labels, GLiNER2/LLM metadata) need human fixes. Corrections must record *who* fixed *what*, *when*, be visibly marked as human-made, and must not be silently clobbered by the machine pipeline.

## 1. Current state (investigated 2026-07-14)

What already exists:
- Per-field human edit endpoints: `PATCH /artifacts/{id}/title_mention`, `/tag_mentions`, `/summary_candidate`; `PATCH /pages/{id}/tag_mentions`, `/text_mention`, `/summary_candidate`; `POST /pages/{id}/compound_mentions` (append-only). All gated on workspace + entity `edit` permission. **None record the actor.**
- Identity is in hand: `RequestAuth` (sentinel-auth-sdk 0.15.0) exposes `user_id`, `email`, `name` from the JWT; use cases receive it but drop it before the aggregate.
- RBAC action-gate pattern: `require_action(auth, "artifacts:create")` (`interfaces/api/routes/helpers.py:90`) + `SERVICE_ACTIONS` registration (`infrastructure/auth.py:12`). Admin/owner bypass built in.
- Summary HIL half-exists: `SummaryCandidate.is_locked` + `hil_correction`; re-summarization skips locked summaries. No equivalent for title/date/tags/authors/compounds.

Gaps (the feature):
1. **No provenance**: no event, aggregate field, read model, or DTO stores who corrected a value or that a human did. `ExtractionMetadata` carries machine provenance only (`model_name`, `confidence`, `pipeline_run_id`).
2. **Machine clobbers human edits**: `ExtractDocumentMetadataUseCase` overwrites title/authors/date unconditionally whenever extraction yields a value (re-run of `POST /artifacts/{id}/extract-metadata` wipes manual fixes). `AggregateArtifactTagsUseCase` recomputes artifact tags wholesale on **every** `Page.TagMentionsUpdated`. CSER re-extraction/label-reconcile rewrites page compound mentions.
3. Missing endpoints: no artifact `presentation_date`/`author_mentions` edit; no replace/delete for page compound mentions (append only).
4. No FE edit UI at all; no "corrected by human" marker.

## 2. What humans can correct (v1)

| Field | Level | Why |
|---|---|---|
| Title | Artifact | OCR/LLM title extraction errors |
| Presentation date | Artifact | Date parse errors (regex/GLiNER2/filename) |
| Tags (incl. compound-name/target/disease entities) | Artifact | NER errors |
| Authors | Artifact | GLiNER2/LLM extraction errors |
| Compound mentions — label (`extracted_id`) + SMILES, add/remove/edit | Page | CSER OCR errors (e.g. the `CMX41O`→`CMX410` O/0 class) |

Out of scope for v1 (deliberate):
- **Summaries** — separate, half-built HIL path (`is_locked`/`hil_correction`); unify later.
- **Page-level tags / extracted text** — artifact tags are the user-facing search surface; text edits would cascade re-embedding for marginal value.
- **Un-correcting** (returning a field to machine control) — follow-up; would be a `DELETE` on the correction.

## 3. Approaches considered

**A. Reuse existing value events + one new provenance event per aggregate (chosen).**
Human correction triggers the *existing* `TagMentionsUpdated`/`TitleMentionUpdated`/etc. event (so every existing projector, Qdrant sync, and pipeline reaction works untouched) **plus** a new `HumanCorrectionRecorded` event carrying `corrected_fields`, `corrected_by_id`, `corrected_by_name`, `corrected_at`. Both saved atomically. Zero changes to existing event schemas.

**B. Add actor fields to the existing `*Updated` events.** Rejected: eventsourcing 9.5.2 rehydrates stored events via `object.__new__` + raw state dict — old events would lack the new attributes; the repo uses no `class_version`/upcasters, so this risks breaking replay of every existing stream for a cosmetic gain.

**C. HIL fields on `ExtractionMetadata` (per-VO provenance).** Pydantic decode is default-safe, and provenance would auto-flow into Mongo/DTOs. Rejected: list fields (tags, compounds) get mushy semantics (mixed human/machine items), the guard and badge logic must derive field-level state from item scans, and the audit record is smeared across VO copies instead of being one explicit event.

## 4. Design

### Domain
- `Artifact.HumanCorrectionRecorded(corrected_fields: list[str], corrected_by_id: str, corrected_by_name: str | None, corrected_at: datetime)`; Page equivalent additionally carries `artifact_id`/`workspace_id` (page-event convention).
- New aggregate state `self.human_corrections: dict[str, dict]` (field → `{corrected_by_id, corrected_by_name, corrected_at}`), initialized in `__init__` — safe for existing streams (no snapshots; replay always runs `__init__`).
- **Guards (machine path)**: `update_title_mention`, `update_tag_mentions`, `update_author_mentions`, `update_presentation_date` (Artifact) and `update_compound_mentions` (Page) become silent no-ops when their field key is in `human_corrections`. Machine callers (metadata extraction, tag aggregation, CSER, label reconciliation) are untouched and simply stop overwriting corrected fields. Human wins permanently (until un-correct ships).
- **Human path**: `Artifact.correct_metadata(...)` (UNSET-sentinel kwargs for title/tags/authors/date; `None` clears a clearable field) and `Page.correct_compound_mentions(...)` trigger the value events directly + one `HumanCorrectionRecorded`.
- Human-built VOs: machine metadata left `None`; `PresentationDate.source="human"` (consistent with existing `gliner2|regex|llm|filename` vocabulary). Tags submitted as `{tag, entity_type}`; ones matching an existing mention (normalized tag + entity_type) keep the existing rich mention (sources, confidences); new ones are fresh mentions. Authors likewise by name. Compound mentions are full-replace; SMILES re-validated/canonicalized via the existing `smiles_validator` port; invalid SMILES → 400.

### Application + API
- `CorrectArtifactMetadataUseCase`, `CorrectPageCompoundMentionsUseCase`: require auth (401 if absent), `require_editor` + workspace check, call aggregate, save, return mapped response.
- `AuthContext` protocol gains `name: str` (the concrete `RequestAuth` already has it).
- Routes:
  - `PATCH /artifacts/{artifact_id}/metadata` — body with optional `title`, `presentation_date`, `tags`, `authors` (pydantic `model_fields_set` distinguishes omitted vs null).
  - `PUT /pages/{page_id}/compound_mentions` — full corrected list.
  - Both: `require_action(auth, "artifacts:hiledit")` + workspace + entity `edit` gates.
- New RBAC action `artifacts:hiledit` added to `SERVICE_ACTIONS`. **Prod note:** Sentinel grants no actions by default — roles must be seeded (same operational step as `artifacts:create`).
- The old per-field artifact PATCH routes `title_mention`/`tag_mentions` (and their use cases) are removed if nothing consumes them (FE doesn't): they would silently no-op after a correction and record no provenance — a trap. `summary_candidate` PATCH stays (separate summary-HIL path).

### Read models / DTOs
- Projectors handle the two new events: `$set {"human_corrections.<field>": {corrected_by_id, corrected_by_name, corrected_at}}` (dotted path — corrections accumulate per field).
- `ArtifactResponse`/`PageResponse` gain `human_corrections: dict[str, HumanCorrectionInfo] | None`; mappers (aggregate→DTO) and Mongo read path both populate it. Flows into OpenAPI → FE types.
- Qdrant: no payload change; corrected values sync via the reused events exactly like machine updates (tags/authors/date → `SyncArtifactMetadataToVectorStoreUseCase`; compound mentions → SMILES re-embedding + label indexes).

### Frontend
- **Edit metadata dialog** (document detail header, pencil button): title `Input`, native `<input type="date">`, tags chip-input (reuse `TagFilter` autocomplete), authors plain chip-input. Sends one `PATCH /artifacts/{id}/metadata`; invalidates `queryKeys.artifacts.detail`.
- **Compound editor** (page detail, per `CompoundGrid` card): edit (label + SMILES with `MoleculeStructure` live preview), delete, add. Sends `PUT /pages/{id}/compound_mentions`; invalidates page detail.
- **`HumanCorrectedBadge`**: small icon + tooltip "Corrected by {name} · {date}" rendered next to any field present in `human_corrections`.
- Gating: edit affordances shown for `useAuthzHasRole("editor")` (no FE action-check primitive exists; the BE 403s without `artifacts:hiledit` and the UI toasts it). A real action-check hook is a follow-up.
- `packages/types` hand-mirrors updated; `pnpm generate` regenerates the api-client schema.

### Answer to "does the backend support storing who corrected it?"
Today: **no** — actor is dropped at the use-case boundary. After this change: **yes, twice over** — immutably in the event store (`HumanCorrectionRecorded` events are a permanent audit log with id, name, timestamp, fields) and queryably in the read models/API for the UI badge.

## 5. Testing
- Domain: guard no-ops after correction; correct_* emits both events; re-correction overwrites provenance; deleted-aggregate rejection.
- Application: provenance recorded from auth; machine use cases skip corrected fields end-to-end; SMILES validation failure → validation error; tag-merge preserves existing rich mentions.
- Projector: new events → `human_corrections.<field>` subdocument.
- API: 401 no auth / 403 without action (admin bypass) / 200 happy path; omitted-vs-null semantics.
- FE: typecheck + build; manual browser pass post-deploy.

## 6. Rollout
- No data migration: new event types only, additive read-model field, additive DTO fields.
- Existing docs: corrections apply from the moment a human makes one; prior machine values stay machine-owned.
- Deploy order: services before web (as usual). Seed `artifacts:hiledit` on appropriate Sentinel roles for prod (`docu-store`) and dev (`docu-store-dev`).

## 7. Follow-ups (not in v1)
- Un-correct (`DELETE` a correction → field returns to machine control, next pipeline run repopulates).
- Unify summary HIL (`is_locked`/`hil_correction`) with `human_corrections`.
- FE object-action permission hook (needs sentinel JS/React SDK support).
- Correction history view (the event stream already holds it; needs a query endpoint).
