from qdrant_client import models

from infrastructure.vector_stores.qdrant_store import QdrantStore


def _keys(flt: models.Filter) -> list[str]:
    out = []
    for cond in (flt.must or []):
        if isinstance(cond, models.FieldCondition):
            out.append(cond.key)
        elif isinstance(cond, models.Filter):
            for sub in (cond.should or []):
                if isinstance(sub, models.FieldCondition):
                    out.append(sub.key)
    return out


def test_build_filter_includes_structure_conditions():
    store = QdrantStore(collection_name="t")
    flt = store._build_filter(
        block_types=["table"], section="Methods", is_table=True, is_figure=None,
    )
    keys = _keys(flt)
    assert "block_type" in keys
    assert "section_path_normalized" in keys
    assert "is_table" in keys
    assert "is_figure" not in keys  # None → omitted


def test_build_filter_none_when_empty():
    store = QdrantStore(collection_name="t")
    assert store._build_filter() is None
