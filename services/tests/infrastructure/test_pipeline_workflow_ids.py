"""pipeline_workflow_ids: the full id set the pipeline runs for one artifact."""

from __future__ import annotations

from uuid import uuid4

from infrastructure.temporal.orchestrator import pipeline_workflow_ids


def test_pipeline_ids_cover_artifact_and_page_workflows() -> None:
    a, p1, p2 = uuid4(), uuid4(), uuid4()
    ids = pipeline_workflow_ids(a, [p1, p2])
    assert len(ids) == 6 + 2 * 7
    assert ids["parse"] == f"artifact-parse-{a}"
    assert ids["doc_metadata"] == f"doc-metadata-{a}"
    assert ids["tag_aggregation"] == f"artifact-tag-aggregation-{a}"
    assert ids["artifact_summarization"] == f"artifact-summarization-{a}"
    assert ids["artifact_summary_embedding"] == f"artifact-summary-embedding-{a}"
    assert ids["batch_reembed"] == f"batch-reembed-{a}"
    assert ids[f"ner:{p1}"] == f"ner-extraction-{p1}"
    assert ids[f"page_summarization:{p1}"] == f"page-summarization-{p1}"
    assert ids[f"page_summary_embedding:{p1}"] == f"page-summary-embedding-{p1}"
    assert ids[f"embedding:{p2}"] == f"embedding-{p2}"
    assert ids[f"compound_extraction:{p2}"] == f"compound-extraction-{p2}"
    assert ids[f"smiles_embedding:{p2}"] == f"smiles-embedding-{p2}"
    assert ids[f"reconcile_compound_labels:{p2}"] == f"reconcile-compound-labels-{p2}"
    assert len(set(ids.values())) == len(ids)


def test_no_pages_gives_artifact_level_only() -> None:
    assert set(pipeline_workflow_ids(uuid4(), [])) == {
        "parse",
        "doc_metadata",
        "tag_aggregation",
        "artifact_summarization",
        "artifact_summary_embedding",
        "batch_reembed",
    }
