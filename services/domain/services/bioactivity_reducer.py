"""Domain service: associate bioactivity tag mentions with their parent compounds.

Bioactivity entities (IC50, MIC, EC50, etc.) are only meaningful when linked to
a compound.  This service reduces bioactivity TagMentions into the
``additional_model_params["bioactivities"]`` list of their parent compound
TagMention and discards orphan bioactivities.
"""

from __future__ import annotations

from domain.services.compound_alias_resolver import build_alias_map, normalize
from domain.value_objects.tag_mention import TagMention


def associate_bioactivities(
    tag_mentions: list[TagMention],
    alias_map: dict[str, str] | None = None,
) -> list[TagMention]:
    """Reduce bioactivity TagMentions into their parent compound TagMentions.

    Algorithm
    ---------
    1. Partition tags into compounds, bioactivities, and others.
    2. Index compounds by normalised tag name (first occurrence wins).
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

    # Index compounds by normalised name (first occurrence wins on duplicates)
    compound_index: dict[str, int] = {}
    for i, c in enumerate(compounds):
        key = normalize(c.tag)
        if key not in compound_index:
            compound_index[key] = i

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

        assay_type = (params.get("assay_type") or "").strip()
        value = (params.get("value") or "").strip()
        # Skip bioactivities with missing assay type or value, as they are unlikely to be useful in this form
        if not assay_type or not value:
            continue

        activity: dict = {
            "assay_type": assay_type,
            "value": value,
            "unit": params.get("unit", ""),
            "raw_text": bio.tag,
        }
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
