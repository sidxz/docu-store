# Literature Search — evaluation findings and root causes

**Date:** 2026-09-02 · **Branch:** `feat/literature-search` @ `9a10f58`
**Method:** 15 browser runs against `localhost:15000`, plus 2 follow-up probes.
Full run table, per-query Europe PMC queries and independent fact-checks:
`literature-search-eval-2026-09-02.xlsx`.
**Design doc this amends:** `LITERATURE_SEARCH_DESIGN.md`

## What works, and must not regress

Query construction is the strong part, and the design's central bet paid off.
Teaching the field syntax in the tool description rather than leaving the model
to guess produced fielded queries in essentially every run: `AUTH:` reached for
unprompted on an author question, `PUB_YEAR` windows added to a vague one, a
`NOT` operator on a negative-constraint one, era-split `PUB_YEAR` ranges on a
temporal one, and real compound names (`cipargamin OR KAE609 OR SJ733`) supplied
from the model's own knowledge.

Zero hallucinated values across 15 runs — every number sampled was verbatim in a
visible abstract. Every `[n]` citation tested resolved to the right card.
Ingestability bias is confirmed absent: paywalled med-chem papers lead the panel,
which is correct.

Off-domain is a strength, not a weakness. The malaria run was the best of the
survey and the kinase-methods run was 100% grounded.

## RC1 — one hardcoded score disables both ranking and answer verification

`infrastructure/chat/tools/literature_tools.py:127`

```python
similarity_score=1.0,  # Europe PMC ranks; it does not score
```

**Ranking.** In `ContextAssemblyNode._tier_results`, `1.0 > _HIGH_SIM (0.85)`, so
every literature result lands in the HIGH tier. `_apply_budget` then walks them in
arrival order taking the full abstract until `chat_context_budget_chars` (12,000)
is spent, then `break`s.

The proof is a probe that assembled **40** sources where the hits were correction
notices with ~300-char abstracts (40 × 300 = 12,000), against 7–11 everywhere
else where abstracts ran ~1,500. **The number of papers the answer sees is a
function of abstract length. Relevance never enters.**

Measured consequences:

- A benzothiazinone temporal question retrieved 47 post-2020 papers through its
  own `PUB_YEAR:[2020 TO 2026]` queries, assembly kept 10 sources all from
  2015–2019, and the answer then reported that no post-2020 evidence exists.
- A "recent advances in TB drug discovery" question retrieved pretomanid, BPaLM,
  ganfeborole and bedaquiline papers and cited none of them.
- An "InhA inhibitors that are not isoniazid analogues" question searched for
  diazaborines and triclosan analogues, got 50 hits, and assembly discarded them.

**Answer verification.** `inline_verification._needs_llm_verification` returns
`False` whenever `context_meta.avg_relevance_score >= chat_verification_relevance_threshold`
(0.4). That average is the mean of the same hardcoded `1.0`, so it is always
exactly 1.0. Every run in the survey printed "LLM verification skipped" — including
the one that shipped `The IC50 of TAM16 against Pks13 is 0.19 µM.` at 0% citation
coverage and 10% grounding.

**The score scale matters.** Measured on the real failure case, the installed
cross-encoder (`ms-marco-MiniLM-L-12-v2`) returns raw logits, not 0–1:

| Document | logit | sigmoid |
|---|---|---|
| direct InhA inhibitors, anti-tubercular | **+1.23** | 0.774 |
| "Correction to ..." notice | −0.36 | 0.411 |
| HadAB/InhA dual inhibitors | −1.47 | 0.187 |
| INHA biomarkers in preeclampsia | −4.49 | 0.011 |
| INHA and clutch length in Zi Geese | **−7.17** | 0.0008 |

Both wrong-gene papers sort to the bottom by a wide margin, so reranking alone
resolves the homograph problem. But the shared `_HIGH_RERANK = 0.7` /
`_MED_RERANK = 0.4` thresholds are calibrated for a different scale, so literature
needs its own tier cut-points or almost everything lands LOW and is truncated to
200 characters.

## RC2 — an outage is reported to the model as "no results", and the tool description tells it to broaden

`infrastructure/literature/europe_pmc.py:187` — `search()` catches
`LiteratureSourceUnavailableError` and returns `[]`.
`infrastructure/chat/tools/literature_tools.py:115` then returns the string
`"No Europe PMC results for: {query}"`.

And `SEARCH_LITERATURE_DEF` line 53 says, correctly for a genuinely empty result
and disastrously for an outage:

> If a fielded query returns nothing, retry once with the bare terms.

So the bare-natural-language degradation the design was built to prevent is not
emergent — it is documented behaviour firing on an ambiguous signal.
`ToolRegistry.execute` has a generic `except` at `retrieval_tools.py:744` that
would surface the real error, but it never fires because `search()` already
swallowed it.

There is no retry anywhere: `search_or_raise` is a single-shot `httpx` call.

**Measured reliability.** Four separate Europe PMC outage windows in ~50 minutes
of testing. A plain `curl` needed four attempts (503, 503, 502, 200) over ~6
seconds. A three-attempt backoff rescues every failure observed.

Worst observed shape: a cross-target question where all six searches failed
returned `Grounded: True (confidence: 100%)` on zero sources, and the entire
answer was the word **`No`** — indistinguishable from "no such compounds exist".
PubMed independently returns 12 records for the same intersection.

## RC3 — the multi-turn loop exists and is starved by budget accounting

`chat_agent_max_iterations` is 5 and `AgenticRetrievalNode` is a ReAct loop with a
`finish_retrieval` tool. Measured across 17 conversations: **63 of 67 tool calls
happened at `iteration=0`.** The loop reached iteration 3 exactly once — during
the total-outage run, where every search returned nothing so the accumulator
never filled.

`agentic_retrieval.py:90` constructs `RetrievalAccumulator()` with no budget, so
it defaults to `chat_context_budget_chars` (12,000) and is charged the full
abstract of all 25–50 hits per search. `at_capacity` fired 17 times at
`chars=100,477` to `173,485` — one round of 3–4 searches overshoots by 8–14× and
the loop exits before iteration 1.

**Consequence: every query in every run was written blind.** The model never sees
a single result before deciding what to search. This is the common cause behind
the weak queries — four facets searched without feedback, generic nouns ANDed
together with no chance to notice, eras split correctly and never checked.

`RetrievalAccumulator.__init__` already accepts `budget_chars`. Nothing needs to
be built; one value needs to be passed.

## RC4 — 35 of 48 available Europe PMC fields are discarded, including retraction status

`parse_hit` (`europe_pmc.py:158`) reads 13 fields. `resultType=core`, which this
client already requests, returns 48. Unused and load-bearing:

- `pubTypeList.pubType` — contains `"Retracted Publication"`
- `commentCorrectionList.commentCorrection[].type` — `"Retraction in"`,
  `"Erratum in"`, `"Expression of concern in"`, with the notice's own reference
- `citedByCount` — a free authority prior

The tool description teaches `TITLE_ABS`, `AUTH` and `PUB_YEAR` but not
`PUB_TYPE`. Asked whether TB drug-target papers had been retracted, the model
wrote `TITLE_ABS:(retract* OR "expression of concern" OR correction OR erratum)`
— a keyword search for the *word* — and concluded that no such paper is reported
as retracted. Europe PMC returns **101** retracted TB papers for
`PUB_TYPE:"Retracted Publication"`.

The sharp end is not answer quality. **Nothing stops a user ingesting a retracted
paper into the corpus**, where it will be cited as evidence indefinitely. The gate
is a single method — `LiteratureHit.ingest_blocker()` — routed through by both the
use case (`literature_use_cases.py:86`) and `fetch_pdf` (`europe_pmc.py:243`), so
one clause fixes every caller.

## RC5 — corpus NER tags are unused by literature search (DEFERRED)

The tag dictionary holds 5,406 workspace-scoped tags across 15 entity types
(`compound_name` 2172, `assay` 677, `author` 439, `gene_name` 419, `target` 381,
`mechanism_of_action` 203, `disease` 92, `smiles` 31, …), each with
`artifact_count` and `artifact_ids`. `Pks13` is a `target` in 43 artifacts.

`plan.ner_entity_filters` compiles to Qdrant payload filters, and literature has no
Qdrant payload, so the filters apply to nothing. The UI rendered
`NER filters: InhA (target)` while goose and preeclampsia papers passed unfiltered.

**Deferred deliberately.** The measurement above shows the cross-encoder already
separates the wrong-gene papers by ~8 logits. RC1 is expected to subsume the
disambiguation value of NER expansion. Re-measure after RC1 and only build this if
the geese survive.

The part that stays interesting regardless is **novelty scoring** — diffing a
retrieved abstract's entities against the tag dictionary to say *"4 of these
introduce targets your corpus has never seen"*. That is a feature, not a fix, and
nothing else in the market can do it because nothing else knows this corpus.
Europe PMC's own `hasTextMinedTerms` / annotations API should be tried before
running `gliner2` over abstracts locally.

## Non-findings

- No dedup between preprint and published versions of the same study (observed in
  4 runs, burning two context slots each time). Real, cosmetic next to the above.
- Range citations such as `[1–10]` render as plain text, not clickable buttons.
- Panel badge numbering is consistent; uncited assembled sources render unbadged
  between numbered ones by design.

---

# Post-fix results (2026-09-02, commits 020b3b0..6a44ca9)

Five acceptance probes, plus one unplanned probe that a live Europe PMC outage
handed us. Telemetry read from `literature.reranked` / `literature.assembly.done`
and the agentic loop's `iteration=` counters.

| Probe | Criterion | Result |
|---|---|---|
| P1 homograph | no goose / preeclampsia `INHA` paper cited | **PASS** — both present in the panel, neither carries a citation badge; every cited paper is genuine InhA/mycobacterial work |
| P2 temporal | a post-2020 paper is cited and the "none exist" claim is gone | **PASS** (headline) |
| P3 point fact | LLM verification runs, or the answer hedges | **FAIL** — see below, and the cause is not RC1 |
| P4 retraction | model issues `PUB_TYPE:"Retracted Publication"`; retracted cards badged, no Add button | **PASS** |
| P5 multi-turn | at least one `iteration=1` or higher | **PASS** |
| P-outage | (unplanned) behaviour when Europe PMC is down | **PARTIAL** |

## P2 — the failure the plan was built to fix, fixed

Before: assembly kept 10 sources all dated 2015–2019 and the answer stated that
the retrieved sources "contain no studies or resistance findings dated 2020 or
later. Therefore, a source-grounded comparison cannot establish how mechanisms
changed after 2020."

After: citations [4] and [5] are both **2022** papers, and the answer delivers
the comparison it previously called impossible —

- 2010s: target-site resistance at DprE1 Cys387 (C387G/A/S/N/T), plus nitro-group
  reduction in *M. smegmatis*
- Since 2020: indirect, efflux-associated resistance via `rv0678`, the negative
  regulator of the MmpS5/L5 pump, with low-level cross-resistance in clinical
  isolates

Coverage 87% (13/15), grounding 97%. The `rv0678` → MmpS5/MmpL5 efflux story is
real, well-established TB biology and its extension to BTZ043/PBTZ169 is a
genuine post-2020 finding — the answer is scientifically correct, not just
better-shaped.

## P5 — the loop iterates

`at_capacity` fired **0 times** across the probe run, against 17 times in the
original survey. Loop iterations observed: `iteration=0` ×15, `=1` ×5, `=2` ×3,
`=3` ×1. The model now searches, reads what came back, and searches again — P4's
run visibly refined from a broad `PUB_TYPE` sweep into target-specific follow-ups.

## P4 — retraction, end to end

Three searches used `PUB_TYPE:"Retracted Publication"`, the field the tool
description previously did not teach. `TITLE_ABS:"Mycobacterium tuberculosis" AND
PUB_TYPE:"Retracted Publication"` returned **37 hits** — against the pre-fix
answer that "no Mycobacterium tuberculosis drug-target paper is explicitly
reported as retracted." 55 cards rendered the RETRACTED badge and **none of them
offered an Add to library button**.

## NEW DEFECT — the reranker is scored against the raw user message

Measured across two probes:

| Probe | Input | top score | high-relevance | selected | avg |
|---|---|---|---|---|---|
| P1 | `TITLE_ABS:"InhA" AND PUB_YEAR:[2024 TO 2026]` | **0.025** | 0 | 60 | 0.003 |
| P2 | natural-language question | **0.788** | 5 | 10 | 0.465 |

`LiteratureRetrievalNode._rescore` scores each abstract against `question` — the
user's raw message. `ms-marco-MiniLM` is trained on natural-language queries, so
a fielded boolean expression scores near zero against everything. Nothing reaches
the HIGH tier, and because the budget loop now uses `continue`, it backfills with
**60 abstracts truncated to 200 characters** instead of ~10 full ones.

Relative ordering still holds — P1 still demoted the wrong-gene papers correctly —
but the absolute calibration collapses. This matters because the surface
deliberately supports users typing Europe PMC syntax directly.

Fix: prefer `plan.reformulated_query` (the planner already produces a
natural-language restatement of intent) as the rerank query, falling back to
`question`. `plan` is already in scope in `LiteratureRetrievalNode.run`.

## P3 — still fails, and RC1 was not the cause

The answer is unchanged: `The IC₅₀ of TAM16 against Pks13 is 0.19 μM. [2]` at 0%
citation coverage, 10% grounding, "LLM verification skipped".

The spec above (RC1) claimed that fixing the hardcoded `1.0` would re-arm the
verification gate. That was half right, and the correction matters:

`_needs_llm_verification` fires only when coverage < 0.7 AND the query is
factual/comparative AND `avg_relevance_score` < 0.4. `avg_relevance_score` is now
a real number — but on this query the sources genuinely *are* relevant (10 of 12
high), so the gate correctly declines on relevance grounds. What is actually
broken is the **coverage checker**: it scored 0/1 on a sentence that visibly
carries a `[2]` marker.

That checker lives in `infrastructure/chat/nodes/inline_verification.py`, a shared
file this plan deliberately did not touch. Fixing it needs a decision about the
Deep Research boundary.

## P-outage — the dangerous half is fixed, the reporting half is weak

Europe PMC went down mid-probe (a fifth outage window in one day). Observed:

- `tool.literature.source_unavailable` logged, three retries per search
- **No bare-query degradation** — the log shows zero `tool.literature.searched`
  lines; the model did not loosen its fielded query
- No panel rendered
- The answer refused rather than inventing: "Because the source set is empty, I
  cannot reliably summarize recent InhA research…"

That is the failure mode that previously produced a one-word answer of "No",
and it is gone. What remains: the answer says "no relevant source documents were
retrieved" rather than "Europe PMC was unavailable", so the user still cannot
tell an outage from an empty result. The tool's summary tells the model both
things; the model relayed only one. Worth tightening the wording.

Also unchanged: `Grounded: True (confidence: 100%)` and `100% citation coverage
(0/0)` on zero sources. Vacuous truth in the shared verification path — same
boundary decision as P3.

## RC5 decision

P1 passed its criterion: the cross-encoder demoted both wrong-gene `INHA` papers
out of the citation set without any NER assistance. **RC5 (corpus NER query
expansion) stays deferred**, as the plan's Task 8 Step 4 specified.
