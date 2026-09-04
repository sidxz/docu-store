# Literature Stats — design

**Date:** 2026-09-04 · **Gate:** per-message `stats` toggle, off by default
**Amends:** `LITERATURE_SEARCH_DESIGN.md` · **Evidence:** `LITERATURE_SEARCH_EVAL_2026-09-02.md`

Charts in the Literature Search answer, describing the papers a question matches
rather than listing them. One panel per answer, two at most, chosen by the model
for the shape of the question, and only when the reader has turned Stats on.

## Why

The panel shows fifty cards in relevance order. That answers *which papers* and
nothing else. Three questions a scientist actually asks of a result set —
is this field growing, what kind of evidence is this, has the answer to my
question changed — are all answerable from data Europe PMC already returns in
the same response, and none of them are asked today.

The six queries below came from one scientist in testing. They are not the spec,
but they are the reason the panels are conditional: **they do not want the same
picture, and three of them want no timeline at all.**

| Question | Shape | Panel |
|---|---|---|
| Do MmpL3 inhibitors disrupt PMF rather than bind directly? | contested claim | Stance over time |
| Are there SuFEx-based Pks13 inhibitors? | existence | Term decomposition |
| Is ClpC1 a good drug target? | appraisal | Timeline + evidence mix |
| What is isoniazid's mechanism of action? | settled knowledge | Landmarks |
| How do BTZ resistance mechanisms since 2020 differ from the 2010s? | temporal | Timeline, faceted by subject |
| Any new ML papers on drug-likeness? | recency | Timeline, normalised |

## Decisions

| | |
|---|---|
| Gate | Per-message `stats` toggle in the composer, **off by default** |
| Selection | The model picks the panel. One per answer, **two maximum** |
| Data authorship | The **tool** computes every number. The model never writes one |
| Timeline denominator | The **whole match**, not the retrieved page |
| Delivery | A new `ContentBlockDTO` type, exactly as tables and molecules ship |
| Rendering | recharts, already a portal dependency |

### Why the gate exists, and why it is called Stats

Every panel costs at least one extra Europe PMC request; stance costs a model
call over the abstracts, spent against the user's own key. Off by default makes
that a choice rather than a tax on every question.

The label is deliberately modest. Five of the six panels **count the result set
rather than read the papers**, and a word like "Analysis" would promise more
than they do. It sits beside Reasoning in the composer and reads as its sibling:
both name extra work you opt into, both say "slower" in the tooltip.

## The rule that must hold

**The model chooses the chart. It never authors a number.**

This is already how molecule blocks work. `SearchCompoundStructureTool`
(`retrieval_tools.py:591`) looks up the SMILES and emits the block itself; the
model receives only a *text* description so it can talk about the structure.
That split is why no structure has ever been invented.

The alternative — the model emitting chart data inside its answer text for
something downstream to parse — would forfeit the property the evaluation
records as this surface's strongest: **zero hallucinated values across fifteen
runs, every number verbatim in a visible abstract**. It is not worth trading for
a simpler parser.

So: the model chooses the panel and supplies the *queries*. The tool runs them
and emits the counts.

## The timeline denominator

A histogram of the fetched papers is a picture of the reranker, not the field.
This is not a rounding error. Measured 2026-09-04:

| Query | hitCount | First 1000 records returned |
|---|---|---|
| `TITLE_ABS:"machine learning" AND TITLE_ABS:"drug"` | 15,158 | 837 dated 2026, 162 dated 2025 |

Europe PMC's default ordering is relevance, which correlates hard with recency.
A chart built from what retrieval fetched would report that the field began last
year. The era comparison in the benzothiazinone question is likewise
unanswerable from fifty relevance-ranked papers.

**Counts come from the full match**, in two regimes:

- **hitCount ≤ 1000** — one request, `resultType=lite&pageSize=1000`. Returns
  every record's `pubYear`, `citedByCount`, `pubType`, `isOpenAccess` and
  `journalTitle`. ~100 KB, ~2 s measured. This single call feeds the timeline,
  the evidence mix *and* the landmarks panel at full fidelity.
- **hitCount > 1000** — one count-only request per year (`pageSize=1`, read
  `hitCount`). Tiny, parallelisable, exact. No other panel is available in this
  regime, because the records themselves were never fetched.

**The counting query must be the query the search actually ran.** If it broadens
— dropping `TITLE_ABS:`, say — the chart describes a different population than
the cards beneath it, and a reader has no way to see the disagreement. This is
the same trap as the bare-query degradation the tool description already guards
against.

That constraint now binds the subject terms only, and it is **enforced**: the
turn records every query that produced cards (`stats_context.record_searched_query`),
and the tool refuses a facet carrying a quoted phrase no search used. The
measured failure was facets built out of the titles of the papers the search
returned — which passes every other guard while charting a population the answer
never read. A facet query drops its year
filter, because every panel already plots against years — a landmarks panel
narrowed to a recent window would hide the canonical papers it exists to
surface. The chart therefore covers a wider span than the papers listed beside
it, and says so plainly: "All years" beneath the panel. The tool refuses a
facet query that still carries a date clause — `PUB_YEAR`, `FIRST_PDATE`,
`CREATION_DATE` and the rest alike — because a prompt does not hold across an
agent loop. At most three facets, each with a distinct name, refused before any
request.

Two properties the timeline must carry, or it lies by default:

- **The current year is partial.** TB papers: 9,538 in 2025, 7,396 in 2026 so
  far. Unmarked, every chart ends on a false decline.
- **The corpus itself grew 73% in a decade** (Europe PMC records: 1.14 M in
  2015, 1.97 M in 2025). Raw counts rise for everything. A normalise toggle
  offering share-of-all-literature is **deferred** — nothing implements it, and
  raw is the default because scientists think in paper counts.
- **A year with no papers is a year with no papers.** `year_counts` returns only
  years that have records and the bar axis is categorical, so a gap closed up
  silently: thiacetazone resistance spans 1963–2021 across 31 distinct years
  with 28 empty ones inside it, drawn as continuous activity. Every year-axis
  panel is densified across its span before it is emitted.

The read/cited overlay was cut with the provenance strip on 2026-09-04. The gap
it existed to expose is real and large — the answer is written from the 6–23
abstracts that fit the context budget while the chart counts the whole match,
measured at 39,651 counted against 9 assembled — so the **footnote names both**:
*"From 1990 on. Every Europe PMC match (Ferroptosis 31,706), not only the papers
cited above."* A line of text, not a second chart.

## How a chart reaches the chat

Nothing new. Docu Store already has a typed content-block protocol:

1. A tool emits `AgentEvent(type="structured_block", block=ContentBlockDTO(...))`.
2. `chat_use_cases.py:504` collects it, streams it over the existing SSE
   channel, and persists it on the assistant message as `structured_content`.
3. `mongo_chat_repository.py:582` round-trips it, so a reopened conversation
   still shows the chart.
4. `RichContentRenderer.tsx:68` switches on `block.type` and renders a component.

Adding a chart is: one value on the `type` Literal, one payload field, one
`case`, one component. **Streaming, persistence and conversation reopen all come
free**, because blocks already do them.

`ContentBlockDTO` gains a single `chart: ChartSpecDTO | None` field rather than
five loose columns. The DTO already carries `headers`/`rows`/`smiles`/
`bioactivities` side by side and is close to the point where another four would
make it unreadable.

### Chart data never re-enters the model's context

It already cannot, and this must not regress. History is built from
`get_recent_messages` and formatted at `nodes/answer_synthesis.py:89` as
`msg.content[:500]` — **the prose only, truncated**. `structured_content` is
persisted for the UI and never reaches a prompt. Molecule and table blocks have
always worked this way; charts inherit it for free.

That is the right default. A series of 38 year-counts per facet, or 34 landmark
records, would otherwise be replayed on every follow-up turn and grow without
bound, for data the model has no use for — it wrote its answer from the
abstracts, and the chart is a rendering for the human.

The consequence to design around: **a follow-up about the chart cannot see the
chart.** "Why the spike in 2019?" reaches a model with no idea what is on
screen. Two cheap mitigations, in order:

- Keep the tool's **turn-local summary short and shaped**, not a data dump —
  *"PMF facet: 22 papers, flat at 1–2/yr since 2014. Structure facet: 105,
  rising to ~12/yr after 2019."* The model then writes a sentence about the
  shape, and that sentence is what survives into history, inside its 500 chars.
- If chart follow-ups turn out to matter, the model **re-plots**. It is a tool
  and the data is one request away. That is cheaper and less fragile than
  carrying chart state through the conversation.

### Where the flag lives, and why it is a contextvar

`ToolRegistry` is constructed in DI (`container.py:1018`, `:1086`) and is a
**singleton**. A per-message flag therefore cannot gate tool registration the
obvious way, and threading `stats` through `ChatAgentPort.run` would touch the
port, the router and every agent for one boolean — note the router does not even
forward `mode` to the agent, it selects one.

The codebase already solved this for the identical problem. `reasoning` is a
per-message knob that must reach LLM adapters buried in DI, and it travels as a
**contextvar set in the use case and reset in `finally`**
(`infrastructure/llm/reasoning_context.py`, set at `chat_use_cases.py:374`,
reset at `:579`, per-task isolated via `Token`). `stats` follows it exactly.

`ToolRegistry.definitions` reads the contextvar and withholds `plot_literature`
when Stats is off, so the model never sees a tool it may not call and spends no
description tokens on it.

## The panels

The tool description tells the model to draw a panel whenever Stats is on,
rather than leaving the decision to the model's own judgement of which
questions need one. The toggle is already the opt-in; the first live pass with
softer wording drew nothing at all across 54 searches.

**Amended 2026-09-04** after the unconditional wording overshot: asked for
bedaquiline's SMILES string the model said it could not supply one and drew a
publication timeline underneath, which is the worst pairing available. The rule
is now "draw when the question is about a body of literature, skip when it asks
for a single fact about one thing", carved out narrowly on both instruction
surfaces rather than restored to the blanket softness that drew nothing.

~~Provenance strip~~ — removed 2026-09-04 after live testing: a
returned/assembled/cited bar chart was judged not useful to a reader.

~~Term decomposition~~ — cut 2026-09-04 without being built. Its trigger was "the
result set is empty or very thin", which is now a refusal: a panel over three
papers is a picture of the paper list. The dead `"terms"` value was removed from
the DTO and the TS union.

**Model-selected, maximum two:**

| Panel | Cost | Renders when |
|---|---|---|
| Timeline | 1 request per facet ≤1000 matches, else 1 + one per year from 1990 | volume, trend or era comparison is at issue |
| Evidence mix | 1 request when ≤1000, else 3 count-only sweeps over the merged facets | evidence quality is at issue |
| Landmarks | 1 request, any match size (`SORT_CITED:y`) | the knowledge is settled; a trend would mislead |
| Stance over time | 1 batched model call; needs ≤1000 matches and ≤60 records | the question contains a claim |

**Every panel has a floor**, not just a ceiling: timeline 15 papers,
evidence_mix 20, stance 10, landmarks 5. Checked before the dispatch, so a thin
stance costs no classifier call. Below it the tool refuses and the model answers
without a picture.

**No patent band.** Patents carry no `TITLE_ABS`-indexed text — `TITLE_ABS:"PROTAC"
AND SRC:PAT` is 0 against 4.2 M indexed patents — so no fielded facet query the
model is asked to write can ever surface one.

**The maximum is enforced by a counter in the tool, not asked for in the
prompt.** A prompt does not hold across a five-iteration agent loop; a counter
does. The third call returns a refusal the model can read.

### Stance specifically

This panel came from user feedback, not from this analysis, and it is the only
one that answers a question the card list cannot.

- Scored **against the claim in the question**, never for sentiment. Publication
  bias makes abstract sentiment ~always positive; a sentiment timeline is one
  flat band forever.
- Labels: supports / refutes / mixed / **no position**. The last is expected to
  be the largest bucket and is worth seeing — of the 22 papers engaging the
  MmpL3 PMF claim, 8 take no position.
- **One batched call** over the abstracts, not one per paper.
- `structured_extractor` is GLiNER2-shaped span extraction and is the **wrong
  port**. Use the tool-calling LLM with a JSON schema.
- **Show the sentence that decided each label.** Stance is a judgement; a reader
  must be able to overrule it.

Worked example, classified by hand from the real 22 abstracts: the
proton-motive-force explanation dominates through 2018, the 2019 *Direct
Inhibition of MmpL3* paper turns it, and by 2025 a comparison of eleven
inhibitor series reports no membrane-potential effect at all. That arc is the
answer to the question, and no list of cards shows it.

## Seams

| Concern | Location |
|---|---|
| Request flag | `interfaces/api/routes/chat_routes.py:65` — `SendMessageRequest` |
| Flag → pipeline | new `infrastructure/llm/stats_context.py`, pattern: `reasoning_context.py` |
| Set / reset | `application/use_cases/chat_use_cases.py:374`, `:579` |
| Tool gating | `infrastructure/chat/tools/retrieval_tools.py:708` — literature-only early return |
| Tool definitions | `retrieval_tools.py:738` — `definitions` reads the contextvar |
| Block DTO | `application/dtos/chat_dtos.py:95` — `ContentBlockDTO.type` Literal |
| Block collection | `chat_use_cases.py:504` |
| Persistence | `infrastructure/chat/mongo_chat_repository.py:582` |
| Europe PMC counts | `infrastructure/literature/europe_pmc.py` — new count-only method |
| Client send | `web/apps/portal/src/hooks/use-chat.ts:242` |
| Composer toggle | `components/chat/ChatInput.tsx:141` — `ReasoningToggle` is the template |
| Toggle state | `lib/stores/chat-store.ts` — alongside `synthesisOverride` |
| Block type (TS) | `web/packages/types/src/domain/chat.ts:81` |
| Renderer | `components/chat/RichContentRenderer.tsx:68` |
| recharts precedent | `app/[workspace]/settings/stats/page.tsx` |

## Slices

1. **Counts client** — `EuropePmcClient.year_counts()`, both regimes, retried on
   5xx like `search_or_raise`. Pure addition, no caller yet.
2. **Block type** — `chart` on the DTO and the TS type, `ChartBlock.tsx` on
   recharts, `case "chart"` in the renderer. Renders from a fixture; no tool yet.
3. **The gate** — `stats_context`, `SendMessageRequest.stats`, the composer
   toggle, `definitions` filtering. Observable end to end with slice 2's fixture.
4. **`plot_literature`** — timeline, evidence mix, landmarks. The two-call
   maximum, enforced in the tool.
6. **Stance** — the batched classifier and its panel.
7. ~~**Term decomposition**~~ — cut 2026-09-04; thin results are refused instead.

## Checks

- `year_counts` returns exact per-year counts above and below the 1000 boundary,
  against recorded fixtures.
- A chart block round-trips through Mongo and rebuilds on conversation reopen.
- `definitions` withholds `plot_literature` when the contextvar is unset, and the
  contextvar is reset even when the turn raises.
- The third `plot_literature` call in one turn is refused.
- Deep Research is byte-identical with Stats off — pin it, the way
  `test_default_accumulator_budget_is_unchanged_for_the_shared_node` pins the
  shared retrieval node.
- A facet whose subject appears in no search this turn is refused before any
  Europe PMC request.
- A panel under its record floor is refused before the classifier is called.
- A year with no papers is drawn as zero, not closed up.
- The same panel over the same subjects is not redrawn by the grounding retry.

## Deferred

- **Charts filtering the panel.** Clicking a year narrowing the fifty cards is
  the interaction that turns these from decoration into a tool. It is deferred
  only because it needs the panel and the block to share selection state, which
  is a bigger change than any slice above.
- **An ablation setting.** `chat_enable_bioactivity_tool` has a deployment
  toggle so the benchmark suite can compare with and without. Stats does not get
  one yet: the per-message toggle is already off by default, and two gates for
  one feature is one too many. Add it when the eval suite needs the comparison.
- **Chart placement.** Blocks render below the whole answer, under a divider
  (`ChatMessage.tsx:102`). Right for a molecule, arguably wrong for a chart that
  is the headline — but moving them moves molecules too. Leave until someone
  complains.
- **Citation network graphs.** The Europe PMC citations endpoint returned 503
  throughout this survey, layout is expensive, and no decision turns on it.
- **A single sentiment score.** One number over a field is the exact claim the
  literature never supports, and it would be the most quotable thing on screen.
