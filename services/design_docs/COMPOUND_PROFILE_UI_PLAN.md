# Compound Structure↔Activity UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a compound's structure, its NER activity data (bioactivities), and its reference pages together across three UI surfaces (page detail, compounds page, chat), powered by one backend profile capability and one shared UI component.

**Architecture:** New `GetCompoundProfileUseCase` composes the existing structure lookup (`get_compounds_by_extracted_id`) with a workspace-wide bioactivity/reference-page assembly, exposed at `GET /compounds/{name}/profile`. The existing bioactivity table is lifted into a shared **app-local** component (`apps/portal/src/components/ui/BioactivityTable.tsx`) reused by all three surfaces — app-local (not `packages/ui`) because all three consumers are portal components and it avoids the cross-package Tailwind `content`-glob risk. Enabled by the shipped compound-label reconciliation (`extracted_id` == NER `compound_name`).

**Tech Stack:** Python 3.12 (FastAPI, pydantic, `returns`, structlog, DDD + lagom DI), Next.js 16 portal (React, TanStack Query, openapi-fetch, Tailwind), pnpm workspace, pytest.

## Global Constraints

- Backend commands: `cd services && uv run …`. Frontend: `cd web && pnpm …` (portal filter: `pnpm --filter portal …`).
- Bioactivity fields are **only** `{assay_type, value, unit, raw_text}` (all the extraction produces). Do **not** add `target`/`operator` columns — that data does not exist (`bioactivity_reducer.py:70-75`).
- Activity scope = **workspace-wide** (all docs in the workspace where the compound appears), ACL-filtered via `allowed_artifact_ids`.
- F1 (page hint) is **page-detail only** and **frontend-only** (no backend call) — uses `page.compound_mentions` already in the payload.
- Reuse `MoleculeStructure` (`@docu-store/ui`) for all structure rendering; never add a new depiction path.
- Frontend `Bioactivity` type (`packages/types/src/domain/extraction.ts:68-73`) = `{assay_type, value, unit, raw_text}` and MUST stay mirrored with the backend `BioactivityDTO`.
- Working dir for paths below: repo root `/Users/sidx/workspace/docu-store`.

---

## Phase 0 — Backend: compound profile capability

### Task 0.1: Compound profile DTOs

**Files:**
- Create: `services/application/dtos/compound_dtos.py`

**Interfaces:**
- Produces: `BioactivityDTO{assay_type:str, value:str, unit:str|None, raw_text:str|None}`; `CompoundPageRefDTO{page_id:UUID, page_index:int, artifact_id:UUID, artifact_title:str|None}`; `CompoundProfileDTO{name:str, extracted_id:str|None, canonical_smiles:str|None, has_structure:bool, synonyms:list[str], bioactivities:list[BioactivityDTO], reference_pages:list[CompoundPageRefDTO]}`.

- [ ] **Step 1: Write the DTOs**

```python
# services/application/dtos/compound_dtos.py
from uuid import UUID

from pydantic import BaseModel


class BioactivityDTO(BaseModel):
    """One NER-extracted bioactivity row. Mirrors web Bioactivity type."""

    assay_type: str
    value: str
    unit: str | None = None
    raw_text: str | None = None


class CompoundPageRefDTO(BaseModel):
    """A page where the compound was detected."""

    page_id: UUID
    page_index: int
    artifact_id: UUID
    artifact_title: str | None = None


class CompoundProfileDTO(BaseModel):
    """Structure + activity profile for a compound, looked up by name."""

    name: str
    extracted_id: str | None = None
    canonical_smiles: str | None = None
    has_structure: bool = False
    synonyms: list[str] = []
    bioactivities: list[BioactivityDTO] = []
    reference_pages: list[CompoundPageRefDTO] = []
```

- [ ] **Step 2: Verify it imports**

Run: `cd services && uv run python -c "from application.dtos.compound_dtos import CompoundProfileDTO; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add services/application/dtos/compound_dtos.py
git commit -m "feat(compounds): compound profile DTOs"
```

---

### Task 0.2: GetCompoundProfileUseCase

**Files:**
- Create: `services/application/use_cases/compound_profile_use_case.py`
- Test: `services/tests/application/test_compound_profile_use_case.py`

**Interfaces:**
- Consumes: `CompoundVectorStore.get_compounds_by_extracted_id(extracted_id, workspace_id, allowed_artifact_ids) -> list[CompoundSearchResult]` (result has `.canonical_smiles`, `.smiles`, `.extracted_id`); `TagDictionaryReadModel.get_artifact_ids_for_tag(tag, entity_type, workspace_id) -> list[str]`; `PageReadModel.get_pages_by_artifact_ids(list[UUID], workspace_id) -> list[PageResponse]` (page has `.page_id`, `.index`, `.artifact_id`, `.tag_mentions` where each has `.entity_type`, `.tag`, `.additional_model_params`); `ArtifactReadModel.get_artifact_by_id(UUID, workspace_id)` (has `.title_mention.title`, `.source_filename`).
- Produces: `GetCompoundProfileUseCase.execute(name: str, workspace_id: UUID, allowed_artifact_ids: list[UUID] | None) -> CompoundProfileDTO`.

- [ ] **Step 1: Write the failing test**

```python
# services/tests/application/test_compound_profile_use_case.py
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from application.dtos.compound_dtos import CompoundProfileDTO
from application.use_cases.compound_profile_use_case import GetCompoundProfileUseCase


def _tm(entity_type, tag, bioactivities=None, synonyms=None):
    params = {}
    if bioactivities is not None:
        params["bioactivities"] = bioactivities
    if synonyms is not None:
        params["synonyms"] = synonyms
    return SimpleNamespace(entity_type=entity_type, tag=tag, additional_model_params=params)


def _page(page_id, index, artifact_id, tag_mentions):
    return SimpleNamespace(page_id=page_id, index=index, artifact_id=artifact_id, tag_mentions=tag_mentions)


class FakeTagDict:
    def __init__(self, ids):
        self._ids = ids

    async def get_artifact_ids_for_tag(self, tag, entity_type, workspace_id):
        return self._ids


class FakePages:
    def __init__(self, pages):
        self._pages = pages

    async def get_pages_by_artifact_ids(self, ids, workspace_id):
        return self._pages


class FakeArtifacts:
    async def get_artifact_by_id(self, artifact_id, workspace_id):
        return SimpleNamespace(title_mention=SimpleNamespace(title="Deck A"), source_filename="a.pdf")


class FakeCompounds:
    def __init__(self, results):
        self._results = results

    async def get_compounds_by_extracted_id(self, extracted_id, workspace_id, allowed_artifact_ids):
        return self._results


def _make(structures, tag_ids, pages):
    return GetCompoundProfileUseCase(
        tag_dictionary=FakeTagDict(tag_ids),
        page_read_model=FakePages(pages),
        artifact_read_model=FakeArtifacts(),
        compound_vector_store=FakeCompounds(structures),
    )


def test_profile_joins_structure_bioactivities_and_pages():
    aid = uuid4()
    pid = uuid4()
    uc = _make(
        structures=[SimpleNamespace(canonical_smiles="C", smiles="C", extracted_id="CMX410")],
        tag_ids=[str(aid)],
        pages=[_page(pid, 3, aid, [
            _tm("compound_name", "CMX410",
                bioactivities=[{"assay_type": "MIC", "value": "0.5", "unit": "uM", "raw_text": "MIC 0.5 uM"}],
                synonyms="foo, bar"),
        ])],
    )
    dto = asyncio.run(uc.execute("CMX410", uuid4(), None))
    assert isinstance(dto, CompoundProfileDTO)
    assert dto.has_structure is True
    assert dto.canonical_smiles == "C"
    assert dto.extracted_id == "CMX410"
    assert [(b.assay_type, b.value, b.unit) for b in dto.bioactivities] == [("MIC", "0.5", "uM")]
    assert dto.synonyms == ["bar", "foo"]
    assert [(r.page_index, str(r.artifact_id)) for r in dto.reference_pages] == [(3, str(aid))]


def test_profile_dedupes_bioactivities_across_pages():
    aid = uuid4()
    bio = [{"assay_type": "MIC", "value": "0.5", "unit": "uM", "raw_text": "x"}]
    uc = _make(
        structures=[],
        tag_ids=[str(aid)],
        pages=[
            _page(uuid4(), 1, aid, [_tm("compound_name", "CMX410", bioactivities=bio)]),
            _page(uuid4(), 2, aid, [_tm("compound_name", "CMX410", bioactivities=bio)]),
        ],
    )
    dto = asyncio.run(uc.execute("CMX410", uuid4(), None))
    assert dto.has_structure is False
    assert len(dto.bioactivities) == 1
    assert len(dto.reference_pages) == 2  # both pages referenced


def test_profile_empty_for_unknown_name():
    uc = _make(structures=[], tag_ids=[], pages=[])
    dto = asyncio.run(uc.execute("NOPE", uuid4(), None))
    assert dto.has_structure is False
    assert dto.bioactivities == []
    assert dto.reference_pages == []


def test_profile_acl_filters_out_non_allowed_artifacts():
    aid = uuid4()
    uc = _make(
        structures=[],
        tag_ids=[str(aid)],
        pages=[_page(uuid4(), 1, aid, [_tm("compound_name", "CMX410", bioactivities=[{"assay_type": "x", "value": "1"}])])],
    )
    # allowed list excludes aid → no data
    dto = asyncio.run(uc.execute("CMX410", uuid4(), [uuid4()]))
    assert dto.bioactivities == []
    assert dto.reference_pages == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services && uv run pytest tests/application/test_compound_profile_use_case.py -v`
Expected: FAIL — `ModuleNotFoundError: ...compound_profile_use_case`.

- [ ] **Step 3: Write the use case**

```python
# services/application/use_cases/compound_profile_use_case.py
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from application.dtos.compound_dtos import (
    BioactivityDTO,
    CompoundPageRefDTO,
    CompoundProfileDTO,
)

if TYPE_CHECKING:
    from application.ports.compound_vector_store import CompoundVectorStore
    from application.ports.repositories.artifact_read_models import ArtifactReadModel
    from application.ports.repositories.page_read_models import PageReadModel
    from application.ports.repositories.tag_dictionary_read_model import TagDictionaryReadModel

logger = structlog.get_logger()


class GetCompoundProfileUseCase:
    """Structure + workspace-wide activity profile for a compound, looked up by name.

    Composes the compound structure store (SMILES) with the NER bioactivity data
    aggregated across the workspace's documents (tag_dictionary + page tag_mentions),
    ACL-filtered. Unknown names return an empty profile (has_structure=False), never 404.
    """

    def __init__(
        self,
        tag_dictionary: TagDictionaryReadModel,
        page_read_model: PageReadModel,
        artifact_read_model: ArtifactReadModel,
        compound_vector_store: CompoundVectorStore,
    ) -> None:
        self._tag_dict = tag_dictionary
        self._pages = page_read_model
        self._artifacts = artifact_read_model
        self._compounds = compound_vector_store

    async def execute(
        self,
        name: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> CompoundProfileDTO:
        name = (name or "").strip()
        if not name:
            return CompoundProfileDTO(name="", has_structure=False)

        structures = await self._compounds.get_compounds_by_extracted_id(
            extracted_id=name,
            workspace_id=workspace_id,
            allowed_artifact_ids=allowed_artifact_ids,
        )
        canonical_smiles = extracted_id = None
        if structures:
            canonical_smiles = structures[0].canonical_smiles or structures[0].smiles
            extracted_id = structures[0].extracted_id

        bioactivities, synonyms, refs = await self._collect_activity(
            name, workspace_id, allowed_artifact_ids,
        )

        return CompoundProfileDTO(
            name=name,
            extracted_id=extracted_id,
            canonical_smiles=canonical_smiles,
            has_structure=bool(structures),
            synonyms=synonyms,
            bioactivities=bioactivities,
            reference_pages=refs,
        )

    async def _collect_activity(
        self,
        name: str,
        workspace_id: UUID,
        allowed_artifact_ids: list[UUID] | None,
    ) -> tuple[list[BioactivityDTO], list[str], list[CompoundPageRefDTO]]:
        artifact_ids = await self._tag_dict.get_artifact_ids_for_tag(
            name, entity_type="compound_name", workspace_id=workspace_id,
        )
        if not artifact_ids:
            return [], [], []
        matched = set(artifact_ids)
        if allowed_artifact_ids:
            matched &= {str(a) for a in allowed_artifact_ids}
        if not matched:
            return [], [], []
        matched_uuids = [UUID(a) for a in matched]

        titles: dict[str, str | None] = {}
        for aid in matched_uuids:
            try:
                art = await self._artifacts.get_artifact_by_id(aid, workspace_id=workspace_id)
                if art:
                    titles[str(aid)] = (
                        art.title_mention.title if art.title_mention else art.source_filename
                    )
            except Exception:
                logger.warning(
                    "compound_profile.artifact_lookup_failed", artifact_id=str(aid), exc_info=True,
                )

        pages = await self._pages.get_pages_by_artifact_ids(matched_uuids, workspace_id=workspace_id)

        seen: set[tuple[str, str, str]] = set()
        bioactivities: list[BioactivityDTO] = []
        synonyms: set[str] = set()
        refs: list[CompoundPageRefDTO] = []
        lname = name.lower()
        for page in pages:
            page_has = False
            for tm in page.tag_mentions:
                if tm.entity_type == "compound_name" and tm.tag.lower() == lname:
                    page_has = True
                    params = tm.additional_model_params or {}
                    for bio in params.get("bioactivities") or []:
                        key = (bio.get("assay_type", ""), bio.get("value", ""), bio.get("unit", ""))
                        if key in seen:
                            continue
                        seen.add(key)
                        bioactivities.append(
                            BioactivityDTO(
                                assay_type=bio.get("assay_type", ""),
                                value=bio.get("value", ""),
                                unit=bio.get("unit") or None,
                                raw_text=bio.get("raw_text") or None,
                            ),
                        )
                    syn = params.get("synonyms")
                    if isinstance(syn, str) and syn.strip():
                        synonyms.update(s.strip() for s in syn.split(",") if s.strip())
            if page_has:
                refs.append(
                    CompoundPageRefDTO(
                        page_id=page.page_id,
                        page_index=page.index,
                        artifact_id=page.artifact_id,
                        artifact_title=titles.get(str(page.artifact_id)),
                    ),
                )
        return bioactivities, sorted(synonyms), refs
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd services && uv run pytest tests/application/test_compound_profile_use_case.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add services/application/use_cases/compound_profile_use_case.py services/tests/application/test_compound_profile_use_case.py
git commit -m "feat(compounds): GetCompoundProfileUseCase (structure + workspace-wide activity)"
```

> **DRY note (deliberate):** the page-iteration here overlaps ~30 lines with
> `SearchStructuredBioactivityTool.execute` (`retrieval_tools.py:490-535`), which is
> entangled with target-filtering + markdown + RetrievalResult building for chat.
> `// ponytail: leave the chat tool untouched now; unify into one helper only if a
> third caller appears or the two drift.` Refactoring the working chat pipeline mid-
> feature is risk without payoff. (Deviates from spec §4.1 "extract" — reason stated.)

---

### Task 0.3: Route + DI wiring + registration

**Files:**
- Create: `services/interfaces/api/routes/compound_routes.py`
- Modify: `services/interfaces/api/routes/__init__.py`
- Modify: `services/interfaces/api/main.py` (router include, ~:242-253)
- Modify: `services/infrastructure/di/container.py` (register use case)
- Test: `services/tests/interfaces/test_compound_routes.py`

**Interfaces:**
- Consumes: `GetCompoundProfileUseCase` (Task 0.2); `get_container`, `get_auth` (`interfaces/dependencies.py`); `get_allowed_artifact_ids(auth)` (`interfaces/api/routes/helpers.py:51-66`); `RequestAuth.workspace_id`.
- Produces: `GET /compounds/{name}/profile -> CompoundProfileDTO`.

- [ ] **Step 1: Write the route**

Match `page_routes.py:41-55` conventions exactly (imports, `handle_use_case_errors`, DI):

```python
# services/interfaces/api/routes/compound_routes.py
from typing import Annotated

from fastapi import APIRouter, Depends
from lagom import Container
from sentinel_auth import RequestAuth

from application.dtos.compound_dtos import CompoundProfileDTO
from application.use_cases.compound_profile_use_case import GetCompoundProfileUseCase
from interfaces.api.middleware import handle_use_case_errors
from interfaces.api.routes.helpers import get_allowed_artifact_ids
from interfaces.dependencies import get_auth, get_container

router = APIRouter(prefix="/compounds", tags=["compounds"])


@router.get("/{name}/profile")
@handle_use_case_errors
async def get_compound_profile(
    name: str,
    container: Annotated[Container, Depends(get_container)],
    auth: Annotated[RequestAuth, Depends(get_auth)],
) -> CompoundProfileDTO:
    """Structure + workspace-wide activity profile for a compound name."""
    allowed = await get_allowed_artifact_ids(auth)
    use_case = container[GetCompoundProfileUseCase]
    return await use_case.execute(name, auth.workspace_id, allowed)
```

> Verify the exact import path of `handle_use_case_errors` and `RequestAuth` against
> `page_routes.py:1-10` before running — copy them verbatim from there.

- [ ] **Step 2: Register the router**

In `services/interfaces/api/routes/__init__.py`, export `router as compound_router` following the sibling pattern (mirror how `page_router` is exported).
In `services/interfaces/api/main.py` (~:242-253, where `app.include_router(page_router)` etc. live), add `app.include_router(compound_router)`.

- [ ] **Step 3: Wire the use case in the DI container**

In `services/infrastructure/di/container.py`, add the import near the other use-case imports and register after a sibling registration (pattern at `:430`):

```python
    container[GetCompoundProfileUseCase] = lambda c: GetCompoundProfileUseCase(
        tag_dictionary=c[TagDictionaryReadModel],
        page_read_model=c[PageReadModel],
        artifact_read_model=c[ArtifactReadModel],
        compound_vector_store=c[CompoundVectorStore],
    )
```

(`TagDictionaryReadModel`, `PageReadModel`, `ArtifactReadModel`, `CompoundVectorStore` are already imported/registered — confirm and reuse; these are the exact deps `SearchStructuredBioactivityTool` gets at `retrieval_tools.py:772-781`.)

- [ ] **Step 4: Write the route test**

```python
# services/tests/interfaces/test_compound_routes.py
from application.use_cases.compound_profile_use_case import GetCompoundProfileUseCase
from infrastructure.di.container import create_container


def test_container_resolves_compound_profile_use_case():
    container = create_container()
    assert isinstance(container[GetCompoundProfileUseCase], GetCompoundProfileUseCase)


def test_compound_profile_route_registered():
    from interfaces.api.main import app
    paths = {r.path for r in app.routes}
    assert "/compounds/{name}/profile" in paths
```

- [ ] **Step 5: Run + import-smoke**

Run: `cd services && uv run pytest tests/interfaces/test_compound_routes.py -v`
Expected: PASS (2 passed)
Run: `cd services && uv run python -c "import interfaces.api.main"`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add services/interfaces/api/routes/compound_routes.py services/interfaces/api/routes/__init__.py services/interfaces/api/main.py services/infrastructure/di/container.py services/tests/interfaces/test_compound_routes.py
git commit -m "feat(compounds): GET /compounds/{name}/profile route + DI wiring"
```

---

## Phase 1 — Shared FE component + hook

### Task 1.1: Extract shared app-local `BioactivityTable`

**Files:**
- Create: `web/apps/portal/src/components/ui/BioactivityTable.tsx`
- Modify: `web/apps/portal/src/components/EntityTagPanel.tsx` (use shared table, remove local `ActivityTable`)

**Interfaces:**
- Produces: `<BioactivityTable activities={Bioactivity[]} />` from `@/components/ui/BioactivityTable`.

> App-local (not `packages/ui`): all three consumers (EntityTagPanel, CompoundResultCard, MoleculeBlock) are portal components, and app-local avoids depending on the portal Tailwind `content` glob covering `packages/ui`. `Bioactivity` type comes from `@docu-store/types`.

- [ ] **Step 1: Create the shared component** (verbatim from the current local `ActivityTable`, `EntityTagPanel.tsx:143-166`)

```tsx
// web/apps/portal/src/components/ui/BioactivityTable.tsx
import type { Bioactivity } from "@docu-store/types";

export function BioactivityTable({ activities }: { activities: Bioactivity[] }) {
  return (
    <div className="mt-2.5 overflow-hidden rounded-md border border-border-subtle">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border-subtle bg-surface-sunken/50">
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Assay</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Value</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Source</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((a, j) => (
            <tr key={j} className="border-b border-border-subtle last:border-0">
              <td className="px-2 py-1.5 font-mono font-medium text-text-primary">{a.assay_type}</td>
              <td className="px-2 py-1.5 font-mono text-text-primary">{a.value}{a.unit ? ` ${a.unit}` : ""}</td>
              <td className="px-2 py-1.5 text-text-muted">{a.raw_text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Point `EntityTagPanel` at the shared component**

In `web/apps/portal/src/components/EntityTagPanel.tsx`:
- Delete the local `ActivityTable` function (`:141-166`, the `// ── Bioactivity table ──` block).
- Add the import near the top imports (`:1-7`): `import { BioactivityTable } from "@/components/ui/BioactivityTable";`
- In `CompoundCard` (`:199-201`) replace `<ActivityTable activities={activities} />` with `<BioactivityTable activities={activities} />`.

- [ ] **Step 3: Typecheck**

Run: `cd web && pnpm --filter portal exec tsc --noEmit`
Expected: no errors in `EntityTagPanel.tsx`.

- [ ] **Step 4: Commit**

```bash
git add web/apps/portal/src/components/ui/BioactivityTable.tsx web/apps/portal/src/components/EntityTagPanel.tsx
git commit -m "refactor(portal): extract shared BioactivityTable; EntityTagPanel consumes it"
```

---

### Task 1.2: `useCompoundProfile` hook + schema regen

**Files:**
- Modify: `web/packages/api-client/src/schema.d.ts` (regenerated)
- Create: `web/apps/portal/src/hooks/use-compound-profile.ts`
- Modify: `web/apps/portal/src/lib/query-keys.ts` (add `compounds.detail`)

**Interfaces:**
- Consumes: `GET /compounds/{name}/profile` (Task 0.3); `authFetch` (`lib/auth-fetch.ts:10`).
- Produces: `useCompoundProfile(name: string | null | undefined)` → TanStack query of `CompoundProfile` (shape mirrors `CompoundProfileDTO`).

- [ ] **Step 1: Regenerate the API schema** (route must exist + backend importable)

Run: `cd web && pnpm --filter @docu-store/api-client generate` (the `generate` script; see `packages/api-client/src/client.ts:5-6`).
Expected: `schema.d.ts` now contains `/compounds/{name}/profile`.
> If the generator needs a running backend, the API is on `http://localhost:8010` in this environment. If it can't reach the backend, skip typed client and use `authFetch` (next step already does).

- [ ] **Step 2: Add the query key**

In `web/apps/portal/src/lib/query-keys.ts`, add under the keys object (mirror `artifacts.detail(id)` at `:28`):
```ts
  compounds: {
    detail: (name: string) => ["compounds", "detail", name] as const,
  },
```

- [ ] **Step 3: Write the hook** (pattern: `use-artifacts.ts:29-46` + `authFetch` escape hatch `use-artifacts.ts:146-151`)

```ts
// web/apps/portal/src/hooks/use-compound-profile.ts
"use client";

import { useQuery } from "@tanstack/react-query";
import type { Bioactivity } from "@docu-store/types";
import { authFetch } from "@/lib/auth-fetch";
import { queryKeys } from "@/lib/query-keys";

export interface CompoundPageRef {
  page_id: string;
  page_index: number;
  artifact_id: string;
  artifact_title: string | null;
}

export interface CompoundProfile {
  name: string;
  extracted_id: string | null;
  canonical_smiles: string | null;
  has_structure: boolean;
  synonyms: string[];
  bioactivities: Bioactivity[];
  reference_pages: CompoundPageRef[];
}

export function useCompoundProfile(name: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.compounds.detail(name ?? ""),
    queryFn: async (): Promise<CompoundProfile> => {
      const res = await authFetch(`/compounds/${encodeURIComponent(name!)}/profile`);
      if (!res.ok) throw new Error(`Compound profile failed: ${res.status}`);
      return (await res.json()) as CompoundProfile;
    },
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });
}
```

> Confirm `authFetch`'s signature/return against `lib/auth-fetch.ts:10` and its use at
> `use-artifacts.ts:146-151`; match how base URL + auth headers are applied (it already
> prefixes the API base — do not hardcode `:8010`).

- [ ] **Step 4: Typecheck**

Run: `cd web && pnpm --filter portal exec tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/apps/portal/src/hooks/use-compound-profile.ts web/apps/portal/src/lib/query-keys.ts web/packages/api-client/src/schema.d.ts
git commit -m "feat(compounds): useCompoundProfile hook + compounds query key"
```

---

## Phase 2 — F1: page-detail structure hint (frontend-only)

### Task 2.1: Same-page structure thumbnail on `CompoundCard`

**Files:**
- Modify: `web/apps/portal/src/components/EntityTagPanel.tsx` (accept `compoundMentions`, thread to `CompoundCard`, render thumbnail on match)
- Modify: `web/apps/portal/src/app/[workspace]/documents/[id]/pages/[pageId]/page.tsx` (pass `page.compound_mentions`, ~:224-237)

**Interfaces:**
- Consumes: `MoleculeStructure` (`@docu-store/ui`); `CompoundMention` (`@docu-store/types`, has `extracted_id`, `smiles`, `canonical_smiles`); `page.compound_mentions`.

- [ ] **Step 1: Accept compound structures in `EntityTagPanel`**

In `EntityTagPanel.tsx`:
- Add `MoleculeStructure` to the `@docu-store/ui` import (alongside `BioactivityTable` from Task 1.1).
- Extend `EntityTagPanelProps` (`:20-24`):
  ```tsx
  interface EntityTagPanelProps {
    tagMentions: TagMentionItem[];
    workspace: string;
    artifactId: string;
    compoundMentions?: { extracted_id: string | null; smiles: string; canonical_smiles: string | null }[];
  }
  ```
- In `EntityTagPanel(...)` destructure `compoundMentions = []` and build a lookup keyed by a normalized `extracted_id`:
  ```tsx
  const structureByLabel = new Map<string, string>();
  for (const c of compoundMentions) {
    const key = c.extracted_id?.trim().toLowerCase();
    const smiles = c.canonical_smiles || c.smiles;
    if (key && smiles && !structureByLabel.has(key)) structureByLabel.set(key, smiles);
  }
  ```
- Pass `structureSmiles={structureByLabel.get(tm.tag.trim().toLowerCase())}` into each `<CompoundCard .../>` (`:258-266`).

- [ ] **Step 2: Render the thumbnail in `CompoundCard`**

Add `structureSmiles?: string` to `CompoundCard`'s props (`:170-180`). After the header row (`:198`, before the activities block), add:
```tsx
      {structureSmiles && (
        <div className="mt-2 flex justify-center border-t border-emerald-500/10 pt-2" title="Structure on file">
          <MoleculeStructure smiles={structureSmiles} width={160} height={110} />
        </div>
      )}
```
> Post-reconciliation `extracted_id` == the NER `tag`, so the exact lowercase/trim
> match resolves. This is same-page only; no fetch.

- [ ] **Step 3: Pass compound_mentions from the page**

In `pages/[pageId]/page.tsx`, at the `EntityTagPanel` usage (~:224-231), add the prop:
```tsx
        <EntityTagPanel
          tagMentions={page.tag_mentions as ...}   // unchanged
          workspace={workspace}
          artifactId={page.artifact_id}
          compoundMentions={page.compound_mentions ?? []}
        />
```
`page.compound_mentions` is already used at `:235-237` (the `CompoundGrid`), so it is in scope.

- [ ] **Step 4: Typecheck + eyeball**

Run: `cd web && pnpm --filter portal exec tsc --noEmit`
Expected: no errors.
Manual: open a page-detail with a compound whose name matches a structure (e.g. a doc from artifact `78b65c71` on `http://localhost:15000`) → the CompoundCard shows a small 2D structure. A compound name with no same-page structure shows no thumbnail (no error).

- [ ] **Step 5: Commit**

```bash
git add web/apps/portal/src/components/EntityTagPanel.tsx "web/apps/portal/src/app/[workspace]/documents/[id]/pages/[pageId]/page.tsx"
git commit -m "feat(compounds): F1 same-page structure hint on CompoundCard"
```

---

## Phase 3 — F2: compounds-page result expand

### Task 3.1: Expandable result showing activities + reference pages

**Files:**
- Create: `web/apps/portal/src/components/compounds/CompoundResultCard.tsx`
- Modify: `web/apps/portal/src/app/[workspace]/compounds/page.tsx` (use the new card, ~:82-129)

**Interfaces:**
- Consumes: `useCompoundProfile` (Task 1.2); `BioactivityTable` (`@docu-store/ui`); `CompoundSearchResultDTO` (`@docu-store/types`, has `extracted_id`, `smiles`, `similarity_score`, `confidence`, `artifact_id`, `artifact_name`, `page_id`, `page_index`).

- [ ] **Step 1: Extract the current result card + add expand**

Move the per-result `<Card>…</Card>` currently inline at `compounds/page.tsx:84-127` into a new component, then add an expand toggle that fetches the profile on open. Full component:

```tsx
// web/apps/portal/src/components/compounds/CompoundResultCard.tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, Loader2 } from "lucide-react";
import { MoleculeStructure } from "@docu-store/ui";
import type { CompoundSearchResultDTO } from "@docu-store/types";
import { Card } from "@/components/ui/Card";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { CopySmiles } from "@/components/ui/CopySmiles";
import { BioactivityTable } from "@/components/ui/BioactivityTable";
import { useCompoundProfile } from "@/hooks/use-compound-profile";

export function CompoundResultCard({ r, workspace }: { r: CompoundSearchResultDTO; workspace: string }) {
  const [open, setOpen] = useState(false);
  const profile = useCompoundProfile(open ? r.extracted_id : null);

  return (
    <Card>
      <div className="flex justify-center border-b border-border-subtle pb-3 mb-3">
        <MoleculeStructure smiles={r.smiles} width={200} height={140} />
      </div>
      <div className="space-y-2 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-text-muted">Similarity</span>
          <ScoreBadge score={r.similarity_score} variant="pill" />
        </div>
        <CopySmiles smiles={r.smiles} maxWidth="max-w-[160px]" />
        {r.extracted_id && (
          <div className="flex items-center justify-between">
            <span className="text-text-muted">ID</span>
            <span className="font-mono font-medium text-text-primary">{r.extracted_id}</span>
          </div>
        )}
        {r.confidence != null && (
          <div className="flex items-center justify-between">
            <span className="text-text-muted">Confidence</span>
            <ScoreBadge score={r.confidence} variant="pill" />
          </div>
        )}
        <div className="flex items-center justify-between pt-1 border-t border-border-subtle">
          <Link href={`/${workspace}/documents/${r.artifact_id}`} className="text-accent-text hover:underline">
            {r.artifact_name ?? "Document"}
          </Link>
          <Link href={`/${workspace}/documents/${r.artifact_id}/pages/${r.page_id}`} className="text-text-muted hover:text-text-secondary">
            Page {r.page_index}
          </Link>
        </div>

        {r.extracted_id && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="mt-1 flex w-full items-center justify-center gap-1 border-t border-border-subtle pt-2 text-[11px] font-medium text-text-muted transition-colors hover:text-text-primary"
          >
            <ChevronDown className={`size-3 transition-transform ${open ? "rotate-180" : ""}`} />
            {open ? "Hide activity" : "Show activity & sources"}
          </button>
        )}

        {open && (
          <div className="pt-1">
            {profile.isPending && <Loader2 className="mx-auto size-4 animate-spin text-text-muted" />}
            {profile.data && (
              <>
                {profile.data.synonyms.length > 0 && (
                  <p className="mb-1 truncate text-[11px] text-text-muted" title={profile.data.synonyms.join(", ")}>
                    aka {profile.data.synonyms.join(", ")}
                  </p>
                )}
                {profile.data.bioactivities.length > 0 ? (
                  <BioactivityTable activities={profile.data.bioactivities} />
                ) : (
                  <p className="text-[11px] text-text-muted">No activity data on file.</p>
                )}
                {profile.data.reference_pages.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Appears on</p>
                    <div className="flex flex-wrap gap-1">
                      {profile.data.reference_pages.map((p) => (
                        <Link
                          key={p.page_id}
                          href={`/${workspace}/documents/${p.artifact_id}/pages/${p.page_id}`}
                          className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px] text-text-muted hover:text-accent-text"
                          title={p.artifact_title ?? undefined}
                        >
                          p.{p.page_index}
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
```

- [ ] **Step 2: Use it in the compounds page**

In `compounds/page.tsx`, replace the results `.map(...)` body (`:83-128`) with:
```tsx
            {(search.data.results as CompoundSearchResultDTO[]).map((r, i) => (
              <CompoundResultCard key={`${r.smiles}-${i}`} r={r} workspace={workspace} />
            ))}
```
Add the import: `import { CompoundResultCard } from "@/components/compounds/CompoundResultCard";` and remove now-unused imports (`MoleculeStructure`, `ScoreBadge`, `CopySmiles`, `Card` if no longer used elsewhere in the file — verify).

- [ ] **Step 3: Typecheck + eyeball**

Run: `cd web && pnpm --filter portal exec tsc --noEmit`
Expected: no errors.
Manual: compounds page → run a SMILES search → each result has "Show activity & sources"; expanding fetches the profile and renders the `BioactivityTable` + page links (or "No activity data on file.").

- [ ] **Step 4: Commit**

```bash
git add web/apps/portal/src/components/compounds/CompoundResultCard.tsx "web/apps/portal/src/app/[workspace]/compounds/page.tsx"
git commit -m "feat(compounds): F2 expandable compound result with activity + sources"
```

---

## Phase 4 — F3: chat molecule block activity

### Task 4.1: Attach bioactivities to the chat molecule block (backend)

**Files:**
- Modify: `services/application/dtos/chat_dtos.py` (`ContentBlockDTO.bioactivities`, ~:80-91)
- Modify: `services/infrastructure/chat/nodes/agentic_retrieval.py` (join prefetched bioactivities onto the molecule block, ~:168-287)
- Test: `services/tests/infrastructure/test_chat_molecule_bioactivities.py`

**Interfaces:**
- Consumes: `BioactivityDTO` (Task 0.1); the molecule `ContentBlockDTO` built at `retrieval_tools.py:650-661`.
- Produces: `ContentBlockDTO.bioactivities: list[BioactivityDTO] | None`.

- [ ] **Step 1: Add the DTO field**

In `services/application/dtos/chat_dtos.py`, import `BioactivityDTO` and add to `ContentBlockDTO` (after `artifact_id`, `:91`):
```python
    bioactivities: list[BioactivityDTO] | None = None
```
Add near the top imports: `from application.dtos.compound_dtos import BioactivityDTO`.

- [ ] **Step 2: Write the failing test** (join logic — pure)

The join lives in `agentic_retrieval.py run()`. Extract the join into a small pure helper so it is unit-testable, then call it from `run()`:

```python
# services/tests/infrastructure/test_chat_molecule_bioactivities.py
from application.dtos.chat_dtos import ContentBlockDTO
from application.dtos.compound_dtos import BioactivityDTO
from infrastructure.chat.nodes.agentic_retrieval import attach_bioactivities_to_molecule_blocks


def test_attaches_bioactivities_by_label():
    blocks = [ContentBlockDTO(type="molecule", smiles="C", label="CMX410")]
    bios = {"cmx410": [BioactivityDTO(assay_type="MIC", value="0.5", unit="uM")]}
    out = attach_bioactivities_to_molecule_blocks(blocks, bios)
    assert out[0].bioactivities and out[0].bioactivities[0].assay_type == "MIC"


def test_no_match_leaves_none():
    blocks = [ContentBlockDTO(type="molecule", smiles="C", label="OTHER")]
    out = attach_bioactivities_to_molecule_blocks(blocks, {"cmx410": [BioactivityDTO(assay_type="MIC", value="1")]})
    assert out[0].bioactivities is None
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd services && uv run pytest tests/infrastructure/test_chat_molecule_bioactivities.py -v`
Expected: FAIL — `attach_bioactivities_to_molecule_blocks` undefined.

- [ ] **Step 4: Implement the helper + wire it into `run()`**

Add to `services/infrastructure/chat/nodes/agentic_retrieval.py` (module level):
```python
def attach_bioactivities_to_molecule_blocks(blocks, bios_by_name):
    """Attach prefetched bioactivities to molecule blocks by (lowercased) label."""
    for block in blocks:
        if block.type == "molecule" and block.label:
            bios = bios_by_name.get(block.label.strip().lower())
            if bios:
                block.bioactivities = bios
    return blocks
```
In `run()` (both prefetches share scope — `compound_entities` at `:168`, bioactivity at `:172-199`, structure at `:262-287`): build `bios_by_name: dict[str, list[BioactivityDTO]]` from the bioactivity prefetch results (keyed by the compound name, lowercased), and after the structure prefetch produces its molecule `structured_block` events, call the helper on those blocks before they are emitted. Convert the prefetched bioactivity dicts to `BioactivityDTO` using the same `{assay_type, value, unit, raw_text}` keys.
> The molecule events are `AgentEvent(type="structured_block", block=ContentBlockDTO(...))` (`retrieval_tools.py:650-661`); mutate `evt.block` for `type=="molecule"` in the `struct_events` loop (`agentic_retrieval.py:272-273`) before `yield`.

- [ ] **Step 5: Run to verify it passes + suite**

Run: `cd services && uv run pytest tests/infrastructure/test_chat_molecule_bioactivities.py -v`
Expected: PASS (2 passed)
Run: `cd services && uv run pytest tests/ -q`
Expected: full suite green (chat tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add services/application/dtos/chat_dtos.py services/infrastructure/chat/nodes/agentic_retrieval.py services/tests/infrastructure/test_chat_molecule_bioactivities.py
git commit -m "feat(chat): attach compound bioactivities to molecule structured blocks"
```

---

### Task 4.2: Render activity in the chat `MoleculeBlock` (frontend)

**Files:**
- Modify: `web/packages/types/src/domain/chat.ts` (`ContentBlock.bioactivities`, ~:22-32)
- Modify: `web/apps/portal/src/components/chat/RichContentRenderer.tsx` (thread the field, ~:79-91)
- Modify: `web/apps/portal/src/components/chat/MoleculeBlock.tsx` (render expandable table)

**Interfaces:**
- Consumes: `Bioactivity` (`@docu-store/types`); `BioactivityTable` (`@docu-store/ui`).

- [ ] **Step 1: Add the field to the mirrored type**

In `web/packages/types/src/domain/chat.ts`, import `Bioactivity` and add to `ContentBlock` (after `artifact_id`, `:31`):
```ts
import type { Bioactivity } from "./extraction";
// ... inside ContentBlock:
  bioactivities: Bioactivity[] | null;
```

- [ ] **Step 2: Thread the field through the renderer**

In `RichContentRenderer.tsx`, in the `case "molecule"` block (`:80-90`), add to the `<MoleculeBlock>` props:
```tsx
            bioactivities={block.bioactivities ?? undefined}
```

- [ ] **Step 3: Render the table in `MoleculeBlock`**

In `web/apps/portal/src/components/chat/MoleculeBlock.tsx`:
- Add imports: `import { useState } from "react";`, `import { BioactivityTable } from "@/components/ui/BioactivityTable";`, and `import type { Bioactivity } from "@docu-store/types";`
- Extend props: `bioactivities?: Bioactivity[];`
- After the "View source page" link (`:45`), before the closing `</div>`, add:
```tsx
      {bioactivities && bioactivities.length > 0 && (
        <ActivityDisclosure activities={bioactivities} />
      )}
```
- Add the disclosure component in the same file:
```tsx
function ActivityDisclosure({ activities }: { activities: Bioactivity[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="mx-auto block text-xs text-primary hover:underline"
      >
        {open ? "Hide activity" : `Show activity (${activities.length})`}
      </button>
      {open && <BioactivityTable activities={activities} />}
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

Run: `cd web && pnpm --filter portal exec tsc --noEmit`
Expected: no errors (both `packages/types` and portal compile).

- [ ] **Step 5: Commit**

```bash
git add web/packages/types/src/domain/chat.ts web/apps/portal/src/components/chat/RichContentRenderer.tsx web/apps/portal/src/components/chat/MoleculeBlock.tsx
git commit -m "feat(chat): expandable activity table under molecule blocks"
```

---

## Self-review checklist (for the implementer)

- Bioactivity fields stay `{assay_type, value, unit, raw_text}` everywhere (DTO ↔ TS `Bioactivity` ↔ `BioactivityTable`). No target/operator.
- `BioactivityDTO` (Task 0.1) is the single source; `ContentBlockDTO.bioactivities` (4.1) and the profile (0.2) both use it; the web `Bioactivity` type mirrors it.
- Workspace/ACL: the use case (0.2) and route (0.3) always pass `workspace_id` + `allowed_artifact_ids`; F1 (2.1) does no fetch (same-page only).
- Shared `BioactivityTable` (1.1) is the only bioactivity table — used by EntityTagPanel, CompoundResultCard (F2), MoleculeBlock (F3).
- `useCompoundProfile` uses `authFetch` until `pnpm generate` lands the typed path.

## Phasing / shippability

Each phase is independently shippable: Phase 0 (backend endpoint, testable via curl), Phase 1 (no behavior change — refactor + hook), Phase 2 (F1 visible), Phase 3 (F2 visible), Phase 4 (F3 visible). Recommended order 0→1→2→3→4; F1 (Phase 2) can ship before the backend if needed (it has no backend dependency).
