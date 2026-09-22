"""Entity filters match tag_normalized, so it must carry every name a question may use."""

from datetime import UTC, datetime
from types import SimpleNamespace

from application.use_cases.page_payload import artifact_tag_normalized, filter_names
from application.use_cases.vector_metadata_use_cases import _build_tag_payload
from domain.value_objects.tag_mention import TagMention


def _tm(tag: str, entity_type: str, synonyms: str | None = None) -> TagMention:
    return TagMention(
        tag=tag,
        entity_type=entity_type,
        confidence=None,
        date_extracted=datetime.now(UTC),
        model_name="structflo-ner",
        additional_model_params={"synonyms": synonyms} if synonyms else {},
    )


def test_a_compound_is_findable_by_every_name_it_goes_by():
    """The card is CHEMBL6109008 aka 8l; a question may name either."""
    tags = [_tm("CHEMBL6109008", "compound_name", "8l, None"), _tm("HepG2 MTT", "assay")]
    names = ["chembl6109008", "8l", "hepg2 mtt"]

    assert filter_names(tags) == names
    payload = _build_tag_payload(tags)
    assert payload["tags"] == ["CHEMBL6109008", "HepG2 MTT"]
    assert payload["tag_normalized"] == names
    artifact = SimpleNamespace(tag_mentions=tags, author_mentions=None, presentation_date=None)
    assert artifact_tag_normalized(artifact) == names
