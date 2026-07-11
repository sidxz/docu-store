# Design: Compound structure ↔ activity UI surfacing

**Status:** design — approved decisions locked, ready for `superpowers:writing-plans`.
**Date:** 2026-07-11
**Enabled by:** the compound-label reconciliation (`extracted_id` now == the NER
`compound_name` tag), which makes the name↔structure↔activity join reliable.

---

## 1. Goal

Three UI surfaces that present a compound's **structure**, its **NER-extracted
activity data** (bioactivities), and its **reference pages** together:

1. **Page-detail hint** — on the page's `CompoundCard`, show that a detected
   compound name has a structure on file (same page).
2. **Compounds page** — expand a similarity-search result to show all of that
   compound's activities + reference pages.
3. **Chat molecule block** — when the chat draws a structure, expand it to show
   the compound's activity data when present.

## 2. The unifying insight

All three are one thing from three surfaces: *given a compound (by name/label),
show structure + activities + source pages together.* So the design is **one
backend capability + one shared frontend component**, then three thin surfaces.

## 3. Locked decisions

| Decision | Choice |
|---|---|
| Activity scope (F2, F3) | **Workspace-wide** — all activities for the compound across every doc in the workspace (tag_dictionary aggregation), ref pages span docs. |
| F1 scope | **Page detail only** — same-page match using the page payload; zero backend. |
| Bioactivity fields | Surface what exists: `{assay_type, value, unit, raw_text}`. **`target`/`operator` are NOT in the extracted data** (`bioactivity_reducer.py:70-75`) — out of scope (separate extraction work). |
| DRY | Extract the bioactivity-lookup logic (currently in the chat tool) into a shared use case; extract the bioactivity table into a shared UI component. |

---

## 4. Backend

### 4.1 `GetCompoundProfileUseCase` (new)

`application/use_cases/compound_profile_use_case.py`. Deps (mirror the chat tool's
set, `retrieval_tools.py:772-781`): `TagDictionaryReadModel`, `PageReadModel`,
`ArtifactReadModel`, `CompoundVectorStore`.

```
execute(name: str, workspace_id: UUID, allowed_artifact_ids: list[UUID] | None)
  -> Result[CompoundProfileDTO, AppError]
```

Composition:
- **Structure** — `compound_vector_store.get_compounds_by_extracted_id(name, workspace_id, allowed_artifact_ids)` (already handles name variants + ACL) → `canonical_smiles`, `extracted_id`, `has_structure = bool(results)`.
- **Bioactivities + synonyms + reference pages** — the logic currently inside
  `SearchStructuredBioactivityTool.execute` (`retrieval_tools.py:398-535`):
  `tag_dictionary.get_artifact_ids_for_tag(name, entity_type="compound_name", workspace_id)`
  → ACL intersect → `page_read_model.get_pages_by_artifact_ids(...)` → for each page,
  match `tag_mention.entity_type=="compound_name"` and `tag.lower()==name.lower()`,
  collect `additional_model_params["bioactivities"]` (raw dicts, **not** the markdown
  table the tool builds) + `synonyms` + provenance `(page_id, page_index, artifact_id, artifact_title)`.
  Dedup bioactivities by `(assay_type, value, unit)`.

**Refactor for DRY:** extract this bioactivity assembly out of
`SearchStructuredBioactivityTool` into the use case (or a shared domain/query
helper the tool and use case both call), so the chat pipeline and the REST route
share one implementation. The tool keeps its markdown-formatting for chat context;
the use case returns structured `CompoundProfileDTO`.

### 4.2 DTO

`application/dtos/compound_dtos.py`:

```python
class BioactivityDTO(BaseModel):
    assay_type: str
    value: str
    unit: str | None = None
    raw_text: str | None = None

class CompoundPageRefDTO(BaseModel):
    page_id: UUID
    page_index: int
    artifact_id: UUID
    artifact_title: str | None = None

class CompoundProfileDTO(BaseModel):
    name: str
    extracted_id: str | None = None
    canonical_smiles: str | None = None
    has_structure: bool
    synonyms: list[str] = []
    bioactivities: list[BioactivityDTO] = []
    reference_pages: list[CompoundPageRefDTO] = []
```

### 4.3 Route

`interfaces/api/routes/compound_routes.py` (there are currently **no** compound
routes). Follow `page_routes.py:43-55` conventions:

```
router = APIRouter(prefix="/compounds", tags=["compounds"])

@router.get("/{name}/profile")
@handle_use_case_errors
async def get_compound_profile(
    name: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> CompoundProfileDTO:
    allowed = await get_allowed_artifact_ids(auth)   # helpers.py:51-66
    use_case = container[GetCompoundProfileUseCase]
    result = await use_case.execute(name, auth.workspace_id, allowed)
    ...
```

Register in `interfaces/api/main.py` (~:242-253) + `routes/__init__.py`; wire the
use case in `infrastructure/di/container.py` (~:430 pattern).

### 4.4 Chat molecule block gets bioactivities

- Extend `ContentBlockDTO` (`application/dtos/chat_dtos.py:80-91`) with
  `bioactivities: list[BioactivityDTO] | None = None`.
- In `agentic_retrieval.py` `run()` (both prefetches share scope: `compound_entities`
  at `:168`, bioactivity `:172-199`, structure `:262-287`), join the already-fetched
  bioactivities to the structure's molecule block **by compound name** and populate
  the new field before the block is emitted (`retrieval_tools.py:650-661`).
  No extra lookup — the data is already prefetched in the same method.

---

## 5. Frontend

### 5.1 Shared `BioactivityTable` (extract)

Extract `ActivityTable` (`apps/portal/src/components/EntityTagPanel.tsx:143-166`,
pure Tailwind, props `{ activities: Bioactivity[] }`) into
`packages/ui/src/molecule/BioactivityTable.tsx`; export via `molecule/index.ts` +
`packages/ui/src/index.ts:7-16`. `Bioactivity` type: `packages/types` (`extraction.ts:68-73`).
Refactor `CompoundCard` to consume the shared component (removes duplication).
> Keep `SourceBadges`/page-link routing app-local (`EntityTagPanel.tsx:44-68`) — each
> surface sources refs differently. `// ponytail: extract only the pure table; skip a
> CompoundProfilePanel wrapper until a 2nd caller needs card+synonyms+badges together.`

### 5.2 `useCompoundProfile(name)` hook

`apps/portal/src/hooks/use-compound-profile.ts`, `useQuery` per `useArtifact`
(`use-artifacts.ts:29-46`). `GET /compounds/{name}/profile` is **not in the generated
schema** yet → use `authFetch` (`lib/auth-fetch.ts:10`, precedent `use-artifacts.ts:146-151`)
until `pnpm generate` regenerates `schema.d.ts`, then switch to `apiClient`. Add
`compounds.detail(name)` to `lib/query-keys.ts`.

### 5.3 Feature 1 — page-detail structure hint (frontend-only)

- `pages/[pageId]/page.tsx` already has `page.compound_mentions` in scope (`:235-237`);
  pass it into `EntityTagPanel` alongside `page.tag_mentions`.
- In `CompoundCard`, build a map `extracted_id → compound_mention` and match the card's
  `tag.tag` (post-reconciliation these are equal; use a case-insensitive/trim match for
  the un-reconciled tail). On match, render a small `MoleculeStructure` thumbnail (or a
  badge that expands the structure inline) next to the name. No backend, same-page only.

### 5.4 Feature 2 — compounds page result expand

- `compounds/page.tsx` result cards (`:82-129`) are flat today — add an expand toggle.
- On expand → `useCompoundProfile(result.extracted_id)` → render `BioactivityTable` +
  synonyms + `reference_pages` (links to `/{workspace}/documents/{artifact_id}/pages/{page_id}`).
  Structure is already shown on the card.

### 5.5 Feature 3 — chat molecule block expand

- Extend the `ContentBlock` type (`packages/types/src/domain/chat.ts:22-32`) with
  `bioactivities: Bioactivity[] | null`.
- Thread `block.bioactivities` through `RichContentRenderer.tsx:79-91` into `MoleculeBlock`.
- `MoleculeBlock` (`chat/MoleculeBlock.tsx:14-48`) renders `BioactivityTable` expandably
  when `bioactivities?.length`.

---

## 6. Data flow

```
F1 (page):     page payload {compound_mentions, tag_mentions} → client-side match → thumbnail on CompoundCard
F2 (compounds): result.extracted_id → GET /compounds/{name}/profile → GetCompoundProfileUseCase → BioactivityTable + ref pages
F3 (chat):     agentic_retrieval prefetch (structure + bioactivity) → join by name → ContentBlockDTO.bioactivities → MoleculeBlock → BioactivityTable
```

Backend truth for F2/F3 activities: `tag_dictionary` (workspace-scoped) + page
`tag_mentions[compound_name].additional_model_params.bioactivities`, ACL-filtered.

## 7. Error handling

- Profile endpoint: unknown/never-seen name → `200` with `has_structure=false`,
  empty `bioactivities`/`reference_pages` (not a 404 — "no data" is a valid answer).
- ACL: `get_allowed_artifact_ids(auth)` → `None` (full access) or `$in`-filtered;
  never return cross-workspace data.
- FE: `useCompoundProfile` loading/empty states; F1 renders nothing when no same-page
  structure matches (no error). Invalid SMILES already falls back to raw text in
  `MoleculeStructure`.

## 8. Testing

- **Use case**: name with structure + bioactivities across 2 docs → deduped
  bioactivities, both pages in `reference_pages`, `has_structure=true`; unknown name →
  empty profile, `has_structure=false`; ACL filters out non-allowed artifacts.
- **Route**: 200 shape; workspace/ACL scoping; missing-name behavior.
- **Chat join**: molecule block for a compound with prefetched bioactivities carries
  them; without → `bioactivities=None`.
- **FE**: `BioactivityTable` renders rows from `Bioactivity[]`; `CompoundCard` shows a
  thumbnail only when a same-page `extracted_id` matches; compounds-page expand fetches +
  renders; `MoleculeBlock` shows the table only when bioactivities present.

## 9. Components

**New backend**
- `application/use_cases/compound_profile_use_case.py`
- `application/dtos/compound_dtos.py`
- `interfaces/api/routes/compound_routes.py`
- tests: `tests/application/test_compound_profile_use_case.py`, route test

**Modified backend**
- `infrastructure/chat/tools/retrieval_tools.py` — extract bioactivity assembly (DRY)
- `application/dtos/chat_dtos.py` — `ContentBlockDTO.bioactivities`
- `infrastructure/chat/nodes/agentic_retrieval.py` — join bioactivities onto molecule block
- `interfaces/api/main.py`, `routes/__init__.py`, `infrastructure/di/container.py` — wire route + use case

**New frontend**
- `packages/ui/src/molecule/BioactivityTable.tsx` (+ barrel exports)
- `apps/portal/src/hooks/use-compound-profile.ts`

**Modified frontend**
- `packages/types/src/domain/chat.ts` — `ContentBlock.bioactivities`
- `apps/portal/src/components/EntityTagPanel.tsx` — use shared table; F1 thumbnail; accept `compound_mentions`
- `apps/portal/src/app/[workspace]/documents/[id]/pages/[pageId]/page.tsx` — pass `compound_mentions`
- `apps/portal/src/app/[workspace]/compounds/page.tsx` — expandable result + profile
- `apps/portal/src/components/chat/{MoleculeBlock,RichContentRenderer}.tsx` — render table
- `apps/portal/src/lib/query-keys.ts` — `compounds.detail(name)`
- regenerate `packages/api-client/src/schema.d.ts` via `pnpm generate` after the route exists

## 10. Phasing (implementation order)

- **Phase 0 — backend core**: `GetCompoundProfileUseCase` + DTO + route + DI + DRY refactor of the bioactivity assembly. Independently testable/shippable.
- **Phase 1 — shared FE component + hook**: extract `BioactivityTable`, `useCompoundProfile`, regenerate schema.
- **Phase 2 — F1** (page hint, frontend-only).
- **Phase 3 — F2** (compounds page expand).
- **Phase 4 — F3** (chat molecule block: `ContentBlockDTO`/`ContentBlock` field + join + render).

## 11. Out of scope

- Capturing `target`/`operator` per bioactivity row (extraction/NER work; the data
  doesn't exist yet — the current chat "Target" column is already blank).
- Document-overview structure hint (F1 is page-detail only; overview would reuse the
  profile endpoint later).
- A compounds *list/browse* endpoint (none exists; not needed here).
- Structure editing / new molecule rendering (reuse existing `MoleculeStructure`).
