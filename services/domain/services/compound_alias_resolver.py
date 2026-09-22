"""Domain service: resolve compound aliases declared by NER into one identity.

NER emits an alias twice — once as the primary compound carrying a ``synonyms``
attribute, once as a compound of its own (``CHEMBL4443524 {synonyms: "TAM16"}``
*and* ``TAM16``), because that is what its few-shot examples teach. Nothing read
``synonyms`` as an identity edge, so a page ended up with two compound cards:
the CSER structure on one surface form and the bioactivities on the other.

This service turns the declaration into an edge. One alias map per document is
built once and reused by the bioactivity join and by both merge points (page
level in ``ExtractPageEntitiesUseCase``, artifact level in
``aggregate_tag_mentions``), so an alias declared on slide 3 also merges the
bare mentions on slides 5-20.

Guards, in order of how much damage they prevent:

- Two labels that each have a *different* structure on file never merge, even
  transitively. A hallucinated synonym fusing two analogs silently corrupts SAR,
  which is far worse than leaving a duplicate card on screen.
- The declaring mention is canonical — NER's own notion of which surface form is
  primary — unless it is a deck label ('7a', '12') and the group has any other
  name. Ties break on declaration count, then lexicographically, so the map is
  deterministic for a given page.
- An alias two different compounds both claim is ambiguous, so it is no evidence
  at all and merges nothing. Without this, one slide where twelve compounds each
  carry the extractor's literal ``"None"`` placeholder would fuse all twelve.
- Null placeholders ("None", "N/A") arrive as literal strings from the extractor
  and are never names.
- Numeric-only aliases resolve *inside* a document but are not publishable
  workspace-wide: med-chem decks number their compounds ("(1, TAM16)"), so ``1``
  is a real alias on the page and pure noise in a shared tag dictionary. See
  ``is_publishable_alias``.

Only ``synonyms`` counts as alias evidence today. NER sometimes types a ChEMBL ID as
``accession_number`` rather than ``compound_name``, which leaves the compound card named
for the code name while CSER labelled the structure with the ID — so the card renders
without its structure. Treating compound-database accessions on the same page as a
fourth edge source would close that; deferred.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from domain.value_objects.tag_mention import TagMention

# A deck's own compound label ('7a', '12', 'Compound 9b'), matched against normalized
# forms. Registry IDs and partner codes (SACC-3060, a ChemBridge number) are open-ended
# and not ours to enumerate; the labels are, so the rule demotes these instead.
# ponytail: letter-prefixed series (A12, S3) and primed labels (7a') are not caught;
# add them here if they turn up as card names.
_DECK_LABEL = re.compile(r"(?:compound|cmpd|cpd)?\d{1,3}[a-z]?")


def normalize(name: str) -> str:
    """Lowercase, strip, and collapse whitespace for tag matching."""
    return name.strip().lower().replace(" ", "")


def synonyms_of(tag_mention: TagMention) -> list[str]:
    """The comma-separated ``synonyms`` attribute as a list of surface forms."""
    raw = (tag_mention.additional_model_params or {}).get("synonyms")
    if not isinstance(raw, str):
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


# Null placeholders the extractor writes as literal strings. Not names.
_NON_ALIASES = frozenset({"none", "null", "n/a", "na", "nan", "unknown", "-", "--"})


def is_alias(text: str) -> bool:
    """Whether a surface form could name a compound at all."""
    return bool(text.strip()) and normalize(text) not in _NON_ALIASES


def is_publishable_alias(alias: str) -> bool:
    """Whether an alias means anything outside the document that declared it."""
    stripped = alias.strip()
    return is_alias(alias) and len(stripped) > 1 and not stripped.isdigit()


def build_alias_map(
    tag_mentions: Iterable[TagMention],
    structures: Mapping[str, str | None] | None = None,
) -> dict[str, str]:
    """Map ``normalize(alias) -> normalize(canonical)`` for one document's compounds.

    ``structures`` maps a compound label to its resolved SMILES (CSER's
    ``extracted_id -> canonical_smiles``). Labels whose structures disagree are
    never merged; the check is per-group, so a chain A→B→C cannot smuggle two
    conflicting structures together through an unstructured middle label.
    """
    by_label = {normalize(k): v for k, v in (structures or {}).items() if k and v}

    edges: list[tuple[str, str]] = []
    claimants: defaultdict[str, set[str]] = defaultdict(set)
    for tm in tag_mentions:
        if tm.entity_type != "compound_name" or not is_alias(tm.tag):
            continue
        canonical = normalize(tm.tag)
        for synonym in synonyms_of(tm):
            alias = normalize(synonym)
            if not is_alias(synonym) or alias == canonical:
                continue
            edges.append((alias, canonical))
            claimants[alias].add(canonical)

    # An alias two different compounds both claim identifies neither of them.
    edges = [(alias, canonical) for alias, canonical in edges if len(claimants[alias]) == 1]
    declared: Counter[str] = Counter(canonical for _, canonical in edges)

    parent: dict[str, str] = {}
    root_smiles: dict[str, str | None] = {}

    def find(node: str) -> str:
        if node not in parent:
            parent[node] = node
            root_smiles[node] = by_label.get(node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for alias, canonical in edges:
        alias_root, canonical_root = find(alias), find(canonical)
        if alias_root == canonical_root:
            continue
        alias_smiles, canonical_smiles = root_smiles[alias_root], root_smiles[canonical_root]
        if alias_smiles and canonical_smiles and alias_smiles != canonical_smiles:
            continue  # two structures on file and they disagree — never fuse
        parent[alias_root] = canonical_root
        root_smiles[canonical_root] = canonical_smiles or alias_smiles

    groups: dict[str, list[str]] = defaultdict(list)
    for node in list(parent):
        groups[find(node)].append(node)

    alias_map: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        # A deck label never names the card while the group has any other name:
        # NER declares the registry ID as the synonym of '8d', and '8d' means nothing
        # off the page. Then declaration count — the surface form others were
        # declared against, NER's primary. Lexicographic only breaks genuine ties.
        canonical = min(
            members,
            key=lambda n: (bool(_DECK_LABEL.fullmatch(n)), -declared[n], n),
        )
        for member in members:
            if member != canonical:
                alias_map[member] = canonical
    return alias_map


def union_bioactivities(activity_lists: Iterable[list[dict]]) -> list[dict]:
    """Union one compound's activity lists, one list per mention, in first-seen order.

    The key includes the assay and the strain, so 8t's ">20.0" in HepG2 MTT and in Vero
    NR are two rows, as are an MIC against two strains. Rows without them (older
    extractions, prose that names neither) can still collide, so a row repeated inside
    one list is kept as a separate measurement, while the same row in two lists is one
    fact reported twice (a summary slide, an alias): each key keeps the most copies any
    single list had.
    """
    activities: list[dict] = []
    kept: Counter[tuple[str, str, str, str, str]] = Counter()
    for found in activity_lists:
        seen: Counter[tuple[str, str, str, str, str]] = Counter()
        for activity in found:
            key = (
                activity.get("assay_type", ""),
                activity.get("value", ""),
                activity.get("unit", ""),
                activity.get("assay", ""),
                activity.get("strain", ""),
            )
            seen[key] += 1
            if seen[key] > kept[key]:
                kept[key] += 1
                activities.append(activity)
    return activities


def merge_alias_group(mentions: list[TagMention], canonical: str) -> TagMention:
    """Collapse mentions of one compound into a single TagMention.

    ``canonical`` is the normalized surface form the result should carry. Every
    other surface form in the group becomes a synonym; bioactivities are unioned
    by ``union_bioactivities``.
    """
    preferred = [m for m in mentions if normalize(m.tag) == canonical] or mentions
    base = max(preferred, key=lambda m: m.confidence if m.confidence is not None else -1.0)

    activity_lists: list[list[dict]] = []
    synonyms: set[str] = set()

    for tm in mentions:
        found = (tm.additional_model_params or {}).get("bioactivities")
        if isinstance(found, list):
            activity_lists.append(found)
        synonyms.update(synonyms_of(tm))
        synonyms.add(tm.tag)

    # The canonical can be a form NER only ever declared as a synonym ('8d' carrying
    # its registry ID), so the card takes that spelling rather than the mention's.
    tag = next((s for s in [base.tag, *sorted(synonyms)] if normalize(s) == canonical), base.tag)
    activities = union_bioactivities(activity_lists)
    synonyms = {s for s in synonyms if is_alias(s) and normalize(s) != normalize(tag)}

    params = dict(base.additional_model_params or {})
    if activities:
        params["bioactivities"] = activities
    if synonyms:
        params["synonyms"] = ", ".join(sorted(synonyms))
    return base.model_copy(update={"tag": tag, "additional_model_params": params})


def merge_compound_aliases(
    tag_mentions: list[TagMention],
    alias_map: dict[str, str],
) -> list[TagMention]:
    """Collapse aliased compound mentions in one page's tags into single entries.

    Non-compound tags pass through untouched. Compounds keep first-seen order,
    matching ``associate_bioactivities``, which also returns compounds first.
    """
    if not alias_map:
        return list(tag_mentions)

    groups: dict[str, list[TagMention]] = {}
    others: list[TagMention] = []
    for tm in tag_mentions:
        if tm.entity_type == "compound_name":
            key = normalize(tm.tag)
            groups.setdefault(alias_map.get(key, key), []).append(tm)
        else:
            others.append(tm)

    return [merge_alias_group(members, key) for key, members in groups.items()] + others
