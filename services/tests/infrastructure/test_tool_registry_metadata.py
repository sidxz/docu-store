"""Every retrieval result must name the document it came from.

"Which document is this from" is a property of a result, not of the tool that
produced it, so the registry fills it in on the way out rather than each tool
remembering to. GetPageContentTool and SearchCompoundStructureTool never looked
the artifact up, and the resulting blank reached the model as
`=== Document: "Unknown Document" ===` and the reader as an unnamed source card.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from infrastructure.chat.models import RetrievalResult
from infrastructure.chat.tools.retrieval_tools import ToolRegistry

ARTIFACT = uuid4()
WORKSPACE = uuid4()
OTHER_WORKSPACE = uuid4()


class FakeArtifacts:
    """Mongo read model, scoped the way the real one is."""

    def __init__(self, workspace_id=WORKSPACE, raises: bool = False) -> None:
        self._workspace_id = workspace_id
        self._raises = raises
        self.calls: list = []

    async def get_artifact_by_id(self, artifact_id, workspace_id=None):
        self.calls.append((artifact_id, workspace_id))
        if self._raises:
            msg = "mongo is having a day"
            raise RuntimeError(msg)
        if workspace_id is not None and workspace_id != self._workspace_id:
            return None
        return SimpleNamespace(
            title_mention=SimpleNamespace(title="Next generation RmlA inhibitors"),
            source_filename="DECK-PMC8613358.pdf",
            author_mentions=[SimpleNamespace(name="Sherman")],
            presentation_date=None,
        )


class FakeTool:
    """Stands in for any tool: hands back whatever results it was given."""

    def __init__(self, results: list[RetrievalResult]) -> None:
        self._results = results

    async def execute(self, args, workspace_id, allowed_artifact_ids):  # noqa: ARG002
        return self._results, "summary", []


def _page_fetch(**overrides) -> RetrievalResult:
    """What GetPageContentTool builds: no artifact metadata at all."""
    return RetrievalResult(
        source_type="chunk",
        artifact_id=ARTIFACT,
        page_id=uuid4(),
        page_index=8,
        expanded_text="page text",
        matched_text="page text",
        similarity_score=1.0,
        query_source="tool_page_content",
        **overrides,
    )


def _registry(artifacts, results: list[RetrievalResult]) -> ToolRegistry:
    registry = ToolRegistry(
        hierarchical_search=object(),
        summary_search=object(),
        page_read_model=object(),
        artifact_read_model=artifacts,
    )
    registry._tools["get_page_content"] = FakeTool(results)
    return registry


async def _run(artifacts, results, workspace_id=WORKSPACE):
    registry = _registry(artifacts, results)
    out, _summary, _events = await registry.execute(
        "get_page_content", {}, workspace_id, None,
    )
    return out


@pytest.mark.asyncio
async def test_a_tool_that_leaves_the_document_unnamed_gets_it_filled_in():
    (result,) = await _run(FakeArtifacts(), [_page_fetch()])
    assert result.artifact_title == "Next generation RmlA inhibitors"
    assert result.authors == ["Sherman"]


@pytest.mark.asyncio
async def test_a_title_the_tool_already_resolved_is_left_alone():
    """Search hits arrive named; re-resolving them would be pure round-trips."""
    artifacts = FakeArtifacts()
    (result,) = await _run(artifacts, [_page_fetch(artifact_title="Rhodanine universe")])
    assert result.artifact_title == "Rhodanine universe"
    assert artifacts.calls == []


@pytest.mark.asyncio
async def test_one_lookup_per_document_however_many_pages_came_back():
    """get_artifact_by_id hydrates every page of the artifact -- once is enough."""
    artifacts = FakeArtifacts()
    await _run(artifacts, [_page_fetch(), _page_fetch(), _page_fetch()])
    assert len(artifacts.calls) == 1


@pytest.mark.asyncio
async def test_the_lookup_is_scoped_to_the_caller_workspace():
    """Unscoped, a resolved title would be a cross-tenant read."""
    artifacts = FakeArtifacts(workspace_id=WORKSPACE)
    (result,) = await _run(artifacts, [_page_fetch()], workspace_id=OTHER_WORKSPACE)

    assert artifacts.calls == [(ARTIFACT, OTHER_WORKSPACE)]
    assert result.artifact_title is None


@pytest.mark.asyncio
async def test_a_literature_result_is_never_looked_up():
    """Its artifact_id is a uuid5 of a DOI with nothing stored under it."""
    artifacts = FakeArtifacts()
    paper = _page_fetch().model_copy(
        update={"source_type": "literature", "external_url": "https://doi.org/10.1/x"},
    )
    await _run(artifacts, [paper])
    assert artifacts.calls == []


@pytest.mark.asyncio
async def test_a_failed_lookup_costs_the_title_and_nothing_else():
    """Retrieval must survive a read model that is down."""
    (result,) = await _run(FakeArtifacts(raises=True), [_page_fetch()])
    assert result.artifact_title is None
    assert result.expanded_text == "page text"
