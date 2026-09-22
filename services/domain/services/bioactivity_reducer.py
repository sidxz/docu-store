"""Domain service: associate bioactivity tag mentions with their parent compounds.

Bioactivity entities (IC50, MIC, EC50, etc.) are only meaningful when linked to
a compound.  This service reduces bioactivity TagMentions into the
``additional_model_params["bioactivities"]`` list of their parent compound
TagMention and discards orphan bioactivities.
"""

from __future__ import annotations

from domain.services.compound_alias_resolver import build_alias_map, is_alias, normalize
from domain.value_objects.tag_mention import TagMention


def _stated(params: dict, key: str) -> str:
    """The attribute's text, or "" when NER left it unstated.

    structflo-ner up to 0.6.0 wrote a placeholder ("None") for an unstated field; 0.7.0
    omits it. Rows stored by either version pass through here, so both count as absent.
    """
    text = (params.get(key) or "").strip()
    return text if is_alias(text) else ""


def associate_bioactivities(
    tag_mentions: list[TagMention],
    alias_map: dict[str, str] | None = None,
) -> list[TagMention]:
    """Reduce bioactivity TagMentions into their parent compound TagMentions.

    Algorithm
    ---------
    1. Partition tags into compounds, bioactivities, and others.
    2. Index compounds by alias-resolved name (first occurrence wins).
    3. For each bioactivity whose ``additional_model_params["compound_name"]``
       matches a compound — through ``alias_map``, so a row citing "TAM16" lands
       on the compound that declared TAM16 as its synonym — build a structured
       activity dict and collect it.
    4. Return enriched compounds (with ``bioactivities`` list) + others.
       Bioactivity TagMentions are removed from the output entirely.

    Bioactivities without a ``compound_name`` or whose compound is not in the
    extracted tags are silently discarded.

    ``alias_map`` is built from the same tags when not supplied; callers that can
    see the page's resolved structures should build it themselves so the
    conflicting-structure guard applies.
    """
    if alias_map is None:
        alias_map = build_alias_map(tag_mentions)

    compounds: list[TagMention] = []
    bioactivities: list[TagMention] = []
    others: list[TagMention] = []

    for tm in tag_mentions:
        if tm.entity_type == "bioactivity":
            bioactivities.append(tm)
        elif tm.entity_type == "compound_name":
            compounds.append(tm)
        else:
            others.append(tm)

    if not bioactivities:
        return list(tag_mentions)  # nothing to reduce; return a copy for safety

    # Index compounds by resolved identity (first occurrence wins), so an activity
    # still lands when the canonical name never appears as a mention of its own.
    compound_index: dict[str, int] = {}
    for i, c in enumerate(compounds):
        key = normalize(c.tag)
        compound_index.setdefault(alias_map.get(key, key), i)

    # Collect structured activities per compound index
    activities_per_compound: dict[int, list[dict]] = {}
    for bio in bioactivities:
        params = bio.additional_model_params or {}
        compound_name = params.get("compound_name")
        if not compound_name:
            continue

        key = normalize(compound_name)
        idx = compound_index.get(alias_map.get(key, key))
        if idx is None:
            continue

        assay_type = _stated(params, "assay_type")
        assay = _stated(params, "assay")  # cell line / format / read-out (HepG2 MTT)
        strain = _stated(params, "strain")  # organism / strain / virus (EV71, H37Rv)
        target = _stated(params, "target")  # protein measured against (hERG, hCA XII)
        combination = _stated(params, "combination")  # partner dosed alongside (meropenem)
        value = (params.get("value") or "").strip()
        # A value needs something to hang on: an endpoint, or what it was measured in,
        # against or with (a column headed "FP (µM)", "hERG", "H37Rv" or "meropenem" names
        # that and no endpoint -- before 0.7.0 all of them sat in `assay`, which kept the
        # row). A bare number says nothing.
        if not value or not (assay_type or assay or target or strain or combination):
            continue

        activity: dict = {
            "assay_type": assay_type,
            "value": value,
            "unit": params.get("unit", ""),
            "raw_text": bio.tag,
        }
        for key, text in (
            ("assay", assay),
            ("strain", strain),
            ("target", target),
            ("combination", combination),
        ):
            if text:
                activity[key] = text
        # ponytail: structflo-ner strips footnote markers ('0.3*' -> '0.3'), so the
        # footnote's caveat (disputed, single determination, precipitated) is lost.
        # Upgrade: a `note` attribute in structflo-ner holding the resolved footnote
        # text, passed through here like `assay` (not in the dedupe key) and shown as
        # a tooltip on the value in BioactivityTable.
        activities_per_compound.setdefault(idx, []).append(activity)

    # Build enriched compound TagMentions
    enriched: list[TagMention] = []
    for i, compound in enumerate(compounds):
        activities = activities_per_compound.get(i)
        if activities:
            updated_params = dict(compound.additional_model_params or {})
            updated_params["bioactivities"] = activities
            enriched.append(
                compound.model_copy(update={"additional_model_params": updated_params}),
            )
        else:
            enriched.append(compound)

    return enriched + others
