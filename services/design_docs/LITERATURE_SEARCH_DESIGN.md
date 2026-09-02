# Literature Search — design

**Branch:** `feat/literature-search` · **Date:** 2026-09-01 · **Flag:** `LITERATURE_ENABLED` (default off)

Search external scientific literature from a dedicated chat surface, and ingest
open-access papers into the corpus through the pipeline uploads already use.

## Why a separate surface

Deep Research answers from the workspace corpus. Literature Search answers from
what has been *published*, and its useful action is "add this to the library"
rather than "cite this". Folding both into one chat would mean one agent whose
tools disagree about what a source is. Separate route, separate mode, shared
components.

## Decisions

| | |
|---|---|
| Coverage | Tier A + B — OA full text where it exists, abstract + DOI link where it does not |
| Ingest target | User picks per ingest: **Private** (default) or **Workspace** |
| Retrieval scope | Literature only, plus a DOI dedup check against the existing corpus |
| Ingest boundary | Licence-gated, enforced server-side. ND refused |

## Legal model

Copyright attaches to the **licence of what is persisted**, not to the API it
arrived through. Three tiers:

- **Tier A — persist freely.** PMC Open Access Subset / Europe PMC (CC BY, CC
  BY-NC, CC0), preprint servers, OpenAlex + Crossref metadata (CC0). No key
  required. An NCBI key is free and only lifts the rate limit 3→10 req/s.
- **Tier B — metadata + abstract, link out.** PubMed records. NCBI's terms
  permit retrieval and display; abstract text is frequently still
  publisher-copyrighted. Stored as searchable metadata with a link, never as a
  corpus document. This is what every reference manager does.
- **Tier C — subscription full text** (Elsevier, Wiley, Springer). Requires a
  per-user key, because the entitlement belongs to the user's institution and
  not to DocuStore. **Out of scope**; see Deferred.

Measured coverage (Europe PMC, 2026-08-29): 8.05M OA full-text articles of
48.8M records. OA share by era — 1990s 1%, 2000s 2%, 2010s 20%, 2020-26 42%.
By topic (title/abstract, 2020+): kinase inhibitor 50%, antimalarial 47%,
tuberculosis+inhibitor 45%, medicinal chemistry 31%, SAR+IC50 25%.

Med-chem is the *worst*-covered domain, which is why Tier B is not optional
polish: without it the tool looks empty on exactly the queries this corpus
cares about.

Licence split of the OA corpus: CC BY 6.38M, CC BY-NC-ND 1.58M, CC BY-NC 1.12M,
CC0 69k, CC BY-SA 6.6k, **CC BY-ND 22.6k**. ND is excluded — chunking and
embedding are hard to argue are not derivative works, and ~20% of the open
corpus is not worth the argument.

### `isOpenAccess` is not the gate

Three records from one real query, each breaking the obvious rule:

| Record | `isOpenAccess` | `licence` | Verdict |
|---|---|---|---|
| Research Square preprint | N | `cc by` | licence permits; no full text to fetch |
| Biochemistry 2022 | N (`inEPMC=Y`) | none | free to read, not to mine |
| ACS Omega 2025 | **Y** | `cc by-nc-nd` | open access, still no derivatives |

So the flag both under- and over-approximates. `licence` decides. Ingestable:
`cc by`, `cc by-sa`, `cc0`, `cc by-nc`, `cc by-nc-sa`. Everything else is
link-only, and the refusal lives in the client — a caller that skipped the check
still cannot pull bytes we may not keep.

Full text is fetched as **PDF, not JATS XML**, though the XML is cleaner and
eight times smaller: CSER reads structures off rendered page images, which exist
only in the PDF. Ingesting XML would silently drop compound extraction.

## The fail-open finding

`interfaces/api/routes/helpers.py:57` returns `None` — meaning *no artifact
filtering, workspace-wide* — both when the user has full access **and when Duar
is unavailable**. Private artifacts therefore fail open during a permission
service outage.

That is acceptable for internal documents, where everyone in the workspace is a
colleague. It would not be acceptable for licensed content, and it is the
reason Tier C is deferred rather than merely unbuilt.

It is also what makes `source_class` in the Qdrant payload load-bearing rather
than cosmetic: a payload filter is evaluated **inside Qdrant**, so unlike the
artifact allowlist it cannot fail open.

## Provenance in Qdrant

One new payload field, `source_class` ∈ `internal | literature_oa`, plus
`license` alongside it. KEYWORD-indexed.

Visibility deliberately does **not** go in the payload. ACL is already enforced
via `allowed_artifact_ids`, and duplicating it would create a second source of
truth that drifts.

`source_class` is set once at ingest and never changes, so it lives on the
artifact read model — no new domain event, no aggregate change.

## Seams

| Concern | Location |
|---|---|
| Flag | `services/infrastructure/config.py` (pattern: `chat_enable_bioactivity_tool:622`) |
| Flag → FE | `web/apps/portal/src/app/api/config/route.ts` |
| Chat mode | `services/application/ports/chat_agent.py:26` — add `"literature"` |
| Tool gating | `services/infrastructure/chat/tools/retrieval_tools.py:706-712` |
| Ingest | `ArtifactUploadSaga.execute(stream, UploadBlobRequest(..., source_uri, visibility))` |
| Payload build | `services/application/use_cases/embedding_use_cases.py:263-289` |
| Payload index | `services/infrastructure/vector_stores/qdrant_store.py:115-133` |
| HTTP client shape | `services/plugins/pubchem_enrichment/infrastructure/pubchem_client.py` |
| Sidebar | `web/apps/portal/src/components/layout/Sidebar.tsx:35` |

## Slices

1. **Provenance** — `source_class` + `license` on the artifact read model, into
   `upsert_metadata`, indexed in Qdrant. Independent of everything else.
2. **Flag** — `LITERATURE_ENABLED` through config and `/api/config`.
3. ~~**Client** — `infrastructure/literature/europe_pmc.py`: `search()` and
   `fetch_pdf()`, returning `LiteratureHit`.~~ **Done.** No rate limiter: one
   request per user action. Add one if bulk ingest ever lands.
4. **Ingest** — `IngestLiteratureUseCase`: dedup on `source_uri`, refuse non-OA,
   hand the stream to the upload saga.
5. **Tool + mode** — `SearchLiteratureTool`; `ToolRegistry` exposes only it when
   mode is `literature`.
6. **Frontend** — `/[workspace]/literature`, `LiteratureResultCard` with the
   OA badge and the Private/Workspace ingest split button, flag-gated sidebar
   entry. `ChatPanel` / `MessageList` / `ChatInput` reused unchanged.

## Checks

- Europe PMC parse, against recorded fixtures, for an OA and a closed result
- Ingest refuses a non-OA hit
- Dedup returns the existing artifact instead of re-ingesting
- `source_class` reaches the Qdrant payload

## Deferred

- **Tier C.** Where the med-chem value actually is (~70% of results), and where
  the credential store, the licence review, and the fail-open above all live.
  Revisit only with a real subscriber asking, and address the fail-open first.
- **Bulk ingest.** Every paper runs docling + NER + CSER + embeddings.
  `ensure_within_quota` gates the route, but an "add all results" button would
  spend a month's quota in one click.
- **Corpus contamination.** ChEMBL and human-authored gold sets assume a curated
  corpus. Benchmark runs will need a `source_class = internal` filter to stay
  comparable across time.
