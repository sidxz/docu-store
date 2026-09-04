# Literature Stats — live verification findings

**Date:** 2026-09-04 · **Branch:** `feat/literature-stats` @ `116f502`
**Method:** 7 browser runs against `localhost:15000` (5 with Stats on, 1 with Stats
off, 1 follow-up), plus a reload pass, a Deep Research check and a theme pass.
Tool calls attributed from `services/logs/restart_api.out` after line 12001.
**Design doc this amends:** `LITERATURE_STATS_DESIGN.md`
**Supersedes:** the 2026-09-04 pre-fix pass, which drew a provenance strip on
every answer and zero `plot_literature` calls.

## What works, and must not regress

**The model now draws.** Five Stats-on questions produced five
`tool.literature.plotted` lines. The previous pass produced none. The retrieval
briefing's instruction to plot before `finish_retrieval` is what changed, and it
holds across the agent loop.

**Panel choice tracked the question's shape in 5/5 runs**, with no prompting
beyond the tool description:

| Question | `panel=` | `facets=` | `total=` |
|---|---|---|---|
| MmpL3 PMF vs direct binding | `stance` | 2 | 21 |
| isoniazid mechanism of action | `landmarks` | 1 | 55 |
| BTZ resistance, 2010s vs since 2020 | `timeline` | 2 | 71 |
| new ML papers for drug likeness | `timeline` | 2 | 261 |
| is ClpC1 a good drug target | `stance` | 2 | 52 |

The settled-knowledge question got landmarks and **not** a timeline, which is the
discrimination the design asks for and the one a generic "always chart the years"
implementation would fail.

**The era timeline is the strongest panel.** The BTZ question produced two
series, `2010s` (2010–2019) and `Since 2020` (2020–2026), each drawn from
`PUB_YEAR`-windowed counting queries identical to the ones the search ran, with
the footnote *"Counts are the whole Europe PMC match, not the papers retrieved."*
That is the design's central claim, working.

**Stats off is inert.** `what are known inhibitors of Pks13` with the chip off
rendered the usual answer and comparison table, no chart, and the
`tool.literature.plotted` count stayed at 5. The chip is absent from the Deep
Research composer entirely (only `Research` and `Reasoning` are offered).

**Persistence holds.** A full page reload of two conversations re-rendered their
charts from `structured_content`, with the Verdicts list, the footnote and the
counting queries intact.

**Charts stay out of context, and the answer is better for it.** The follow-up
`why the change in 2019?` in conversation 1 (Stats off) re-searched Europe PMC —
29 found, 6 cited — and answered from abstracts about the 2019 direct-inhibition
papers. It restated no series number. Latency ~75 s, no worse than a first turn.
This is the mitigation the design predicted, and it worked without the re-plot
fallback.

**No prose restated a chart number** in any of the 5 runs. The rule that the
model chooses the panel and never authors a number is intact.

**The current year is drawn faint** on every timeline and stance chart, and the
footnote says so (`2026 is a partial year.`). Correct in both themes.

**Verdicts reads sensibly.** Collapsed by default, and each line is
`year · label · title — "deciding sentence"`, e.g.
`2018 · supports · Novel Acetamide Indirectly Targets Mycobacterial Transporter
MmpL3 by Proton Mot — "E11 indirectly inhibits MmpL3-facilitated translocation of
trehalose monomycolates by proton motive force disruption."` A reader can
overrule the classifier from that line alone.

**Dark mode is correct.** Figure ground `rgb(30,41,59)`, caption and footnote
`rgb(241,245,249)`, bars unchanged and legible. Verified by computed style, not
by eye — the extension's screenshot compositing showed a stale white card twice.

## RC1 — the x-axis label is drawn on top of the legend on every multi-series chart

`web/apps/portal/src/components/chat/ChartBlock.tsx:103` and `:129`

The `XAxis` label is positioned `insideBottom` with `offset: -12` inside a
`bottom: 20` margin, and `<Legend />` is rendered into the same band. Both land
on the same 20 px strip.

Measured on all four multi-series charts drawn in this survey. The legend renders
as overprinted text:

- BTZ timeline: `2010s   Sin[Year]2020`
- ML timeline: `Drug-likeness prediction   Ge[Year]ative drug-like design`
- MmpL3 stance: `mixed   none   ref[Year]tes   supports`
- ClpC1 stance: `none   su[Year]ports`

The single-series landmarks chart is unaffected, because `ChartBlock.tsx:94`
withholds the legend below two series — which is why `Year` is the one axis label
in the survey that renders cleanly.

Both a series name and the axis label are illegible on every chart the feature
was built to draw. This is the most visible defect in the set.

## RC2 — the landmarks panel does not say which papers the landmarks are

`services/infrastructure/chat/tools/literature_stats_tools.py:342`–`:362`,
`web/apps/portal/src/components/chat/ChartBlock.tsx:85`

`_landmarks` sorts to the 40 most-cited records and then emits
`points=[(float(r.year), float(r.cited_by_count))]`. The title, the journal and
the external id are all dropped at that line; `notes` is not set, so the
`Verdicts` disclosure never appears for this panel.

The renderer cannot recover what the tool discarded. `ChartBlock.tsx:85` mounts a
bare `<Tooltip />` on the scatter, so hovering the isoniazid chart's 1998 point
returns:

```
Citations : 482
x : 1998
```

`x` is the raw recharts data key, and there is no paper.

The panel's stated purpose is *"where a timeline is noise and the reader needs
the canonical papers"* (`literature_stats_tools.py:65`). What renders is 40
anonymous dots and a citation axis. A reader who wants the canonical isoniazid
paper cannot get it from this chart — the paper panel beside it is ordered by
relevance, not by the citation count the dots encode, so the chart cannot even be
read against the list.

## RC3 — nothing checks that the counting query is the query that was searched

`literature_stats_tools.py:239` (`_validate_args`)

The design's check list requires *"The counting query equals the search query
that produced the cards"*, and the tool description asks for it in prose
(`literature_stats_tools.py:71`–`:74`). `_validate_args` enforces only the facet
count and the panel name. Nothing compares the facet query to the queries the
turn actually ran.

The MmpL3 run broke it. The three searches logged were:

```
tool.literature.searched hits=19 query='TITLE_ABS:"MmpL3" AND (TITLE_ABS:"proton motive force" OR TITLE_ABS:protonophore OR ...
tool.literature.searched hits=30 query='TITLE_ABS:"MmpL3" AND (TITLE_ABS:binding OR TITLE_ABS:structure OR TITLE_ABS:"target engagement" ...
tool.literature.searched hits=19 query='TITLE_ABS:"MmpL3 inhibitor" AND (TITLE_ABS:resistance OR TITLE_ABS:mutation OR TITLE_ABS:target)'
```

The chart's own footnote reports its counting queries as:

```
TITLE_ABS:"Direct Inhibition of MmpL3" OR TITLE_ABS:"Indirectly Targets Mycobacterial Transporter MmpL3"
TITLE_ABS:"Direct Inhibition of MmpL3" OR TITLE_ABS:"Proton transfer activity"
```

Those are **paper titles**, not the search. The model reached into the retrieved
cards and quoted three of them back as phrase queries. Both facets share their
first clause, so the two "sides" of the claim are not disjoint.

Consequence, measured: the panel header reports `60 found`, the chart scored
`total=21`, and the chart's y-axis never exceeds 2. The picture describes a
population the reader cannot see and did not ask for, and — the trap the design
names — has no way to notice the disagreement.

## RC4 — a recency question truncates its own timeline to three bars

`literature_stats_tools.py:49`–`:80` (the tool description)

`are there any new machine learning papers for drug likeliness` produced a
timeline whose two facet queries both end `AND PUB_YEAR:[2024 TO 2026]`. The
chart is three bars per series: 2024, 2025, 2026.

It does not literally claim the field began this year, so the brief's stated
check passes on its wording. It fails on its purpose. The design's whole argument
for counting the full match is that *"a chart built from what retrieval fetched
would report that the field began last year"* — and a chart whose own window is
three years long reports nothing about growth either way. Worse, the tallest bar
in the ML chart is 2026 (~73 against 63 in 2025), which is the partial year; the
faint fill and the footnote are the only things standing between the reader and
"the field doubled this year".

Root cause is a gap in the description, not in the counting code: nothing tells
the model that the question's recency framing belongs in the *search* window and
not in the *counting* window, and the tool does not widen or strip `PUB_YEAR`
before counting. The two other timeline runs got their windows right because the
question was explicitly comparative.

## RC5 — stance verdict lines are paired to papers by position; the bars are paired by id

`literature_stats_tools.py:407` against `:428`–`:433`

The chart stacks join verdict to paper on the id:

```python
by_id = {v.external_id: v.label for v in verdicts}
```

The `notes` list, two dozen lines below, joins them on position:

```python
notes=[
    f"{hit.year} · {v.label} · {hit.title[:80]} — “{v.evidence}”"
    for hit, v in zip(hits, verdicts, strict=False)
    ...
]
```

`hits` comes from `_core_records`, deduped into a dict; `verdicts` comes from
`classify_stance` over a batched model call. Nothing guarantees the classifier
returns one verdict per hit, in order, and `strict=False` guarantees the
mismatch is silent — the shorter list simply ends the zip. Whenever the
classifier drops or reorders an entry, the bars say one thing and the Verdicts
list attributes the label to a different paper.

Observed in the MmpL3 run: two byte-identical lines,

```
2017 · refutes · MmpL3 is the flippase for mycolic acids in mycobacteria. — "we establish the mechanism-of-action of BM212 as a potent MmpL3 inhibitor"
2017 · refutes · MmpL3 is the flippase for mycolic acids in mycobacteria. — "we establish the mechanism-of-action of BM212 as a potent MmpL3 inhibitor"
```

Two Europe PMC records for one paper would explain the duplicate without a
misalignment, and I could not distinguish the two cases from the browser. The
unsound join is real either way: the panel that exists so a reader can overrule a
judgement must not be able to attribute that judgement to the wrong paper.

## RC6 — the step feed reports every chart as a search that found nothing

`services/infrastructure/chat/nodes/agentic_retrieval.py:640`

Every tool call in the loop is narrated with one format string:

```python
f"Searched: {tc.tool_args.get('query', tc.tool_name)[:80]} "
f"→ {len(tool_results)} results ({new_count} new)"
```

`plot_literature` has no `query` argument and returns no retrieval results, so
the step feed prints, while a chart is being drawn:

```
Searched: plot_literature → 0 results (0 new)
```

Observed on the MmpL3 run. The one line in the UI that tells a reader the chart
is happening tells them it failed.

## RC7 — the stance title is cut mid-word

`literature_stats_tools.py:413` — `title=f"Papers on: {claim[:120]}"`

A hard slice, no ellipsis, no word boundary. The MmpL3 chart is headed:

```
Papers on: MmpL3 inhibitors act primarily by disrupting the proton motive force rather than by directly binding and inhibiting MmpL
```

`MmpL3` truncated to `MmpL`, which in this domain is a different protein family.

## Minor

- **Partial-year fill reads as "dirtier", not "fainter", in dark mode.**
  `ChartBlock.tsx:124` applies `fillOpacity 0.4` against the surface, so on the
  dark ground the 2026 bar darkens to a muddy brown instead of paling. Still
  distinguishable, and the footnote carries the meaning.
- **The conversation header keeps the previous conversation's title** after
  `New Research`, until the first answer lands. Seen on 3 of 5 new conversations.
  Pre-existing, not a Stats defect.
- **The Stats chip resets to off on page reload** but persists across `New
  Research` within a session. Consistent with a per-message toggle; worth
  confirming it is intended, since a reader who reloads mid-survey silently
  loses their charts.

## Latencies

Bounded by a 10 s polling interval, wall clock from send to composer re-enable:

| Run | Panel | Latency |
|---|---|---|
| MmpL3 PMF | stance | ~110 s |
| isoniazid | landmarks | ~60 s |
| BTZ eras | timeline | ~200 s |
| ML drug-likeness | timeline | ~130 s |
| ClpC1 | stance | ~115 s |
| Pks13, Stats off | — | ~85 s |
| 2019 follow-up, Stats off | — | ~75 s |

Stats costs roughly 30–60 s over a Stats-off turn of comparable breadth. The BTZ
run at ~200 s is the outlier and exceeded the 180 s the brief budgeted.

## Not verified

Stated so the next pass does not assume otherwise:

- **The two-panel maximum.** No turn drew more than one panel, including the
  ClpC1 question chosen to tempt several. The counter never reached its ceiling,
  so the third-call refusal path was not exercised.
- **`evidence_mix`.** The model never selected it in 5 runs, so it has not been
  seen rendered against live data.
- **Term decomposition.** Out of scope for this plan; it fires only on thin
  result sets.
- **The normalise / share-of-literature toggle.** Not present in the rendered
  chart; the design lists it as a property the timeline should carry. Whether it
  is unbuilt or gated was not determined.
- **Panel behaviour above the 1000-record boundary.** The largest counting query
  in the survey was `total=261`, so only the exhaustive regime was exercised.
- **Stance classifier failure handling.** No `stance_failed` line appeared, so
  the refusal text was never shown to a reader.

## Deferred

- Charts filtering the paper panel on click — unchanged from the design.
- Chart placement above the prose. The charts render below the whole answer,
  which for the BTZ run put a two-era timeline underneath a conclusion that says
  the sources do not provide enough post-2020 studies. The chart answers that
  sentence and sits below it.
- An ablation setting for the benchmark suite.
- Citation-network panels.
