"""Classifying abstracts against the claim in a question.

Not sentiment. Publication bias makes nearly every abstract positive about its
own result, so a sentiment timeline is one flat band forever and says nothing.
Stance against a specific claim does move, and the movement is the finding.

`structured_extractor` is deliberately not used: GLiNER2 does span extraction,
and this is a judgement over a whole abstract.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from application.ports.llm_client import LLMClientPort
    from infrastructure.literature.europe_pmc import LiteratureHit

log = structlog.get_logger()

STANCE_LABELS = ("supports", "refutes", "mixed", "none")

# Enough of an abstract to judge a claim against, and short enough that fifty of
# them fit one call.
_ABSTRACT_CHARS = 1200

_PROMPT = """\
You are scoring scientific abstracts against ONE claim.

CLAIM: {claim}

For each paper below, decide what it does to that claim:
  supports — its findings argue FOR the claim
  refutes  — its findings argue AGAINST it
  mixed    — it argues both ways, or supports it only under a condition
  none     — it uses the same vocabulary but takes no position on this claim

Most papers are "none". That is expected; do not stretch for a position.

Quote the fragment of the abstract that decided each verdict, verbatim and under
20 words. If nothing in the abstract decides it, the label is "none" and the
evidence is an empty string.

Return ONLY JSON: {{"verdicts": [{{"id": "...", "label": "...", "evidence": "..."}}]}}

PAPERS:
{papers}
"""


@dataclass(frozen=True)
class StanceVerdict:
    """One paper's position on the claim, with the words that decided it."""

    external_id: str
    label: str
    evidence: str


def _papers_block(hits: list[LiteratureHit]) -> str:
    out = []
    for hit in hits:
        body = (hit.abstract or hit.title or "")[:_ABSTRACT_CHARS]
        out.append(f"[id: {hit.external_id}] ({hit.year}) {hit.title}\n{body}\n")
    return "\n".join(out)


def _extract_json(raw: str) -> dict[str, Any] | None:
    """The payload, whether or not the model wrapped it in prose or a fence."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def classify_stance(
    llm: LLMClientPort,
    claim: str,
    hits: list[LiteratureHit],
) -> list[StanceVerdict]:
    """One verdict per hit, in the order given. Empty when the model fails.

    One call for every abstract rather than one call per abstract: this is spent
    against the user's own key, and fifty round trips for one panel is not a
    trade anyone would accept.

    A paper the model skipped comes back as "none" rather than disappearing. A
    silently shorter list would change every total on the chart.
    """
    if not hits:
        return []

    raw = await llm.complete(_PROMPT.format(claim=claim, papers=_papers_block(hits)))
    payload = _extract_json(raw)
    if not payload or not isinstance(payload.get("verdicts"), list):
        log.warning("literature.stance.unparseable", head=raw[:200])
        return []

    by_id: dict[str, tuple[str, str]] = {}
    for entry in payload["verdicts"]:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label", "")).strip().lower()
        if label not in STANCE_LABELS:
            label = "none"
        by_id[str(entry.get("id", ""))] = (label, str(entry.get("evidence", "") or ""))

    return [
        StanceVerdict(
            external_id=hit.external_id,
            label=by_id.get(hit.external_id, ("none", ""))[0],
            evidence=by_id.get(hit.external_id, ("none", ""))[1],
        )
        for hit in hits
    ]
