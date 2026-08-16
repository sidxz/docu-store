"""GetPageContentTool must not leak pages across workspaces.

page_id is a model-controlled (user-steerable) tool arg, so the fetch must be
workspace-scoped. Regression for the cross-tenant read where a full-access
member (allowed_artifact_ids=None) could pull any workspace's page by UUID.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from infrastructure.chat.tools.retrieval_tools import GetPageContentTool


class _WorkspaceScopedPages:
    """Fake PageReadModel that honors workspace_id exactly like the Mongo query:
    a page is returned only when no workspace_id is given OR it matches."""

    def __init__(self, page: SimpleNamespace, page_ws: UUID) -> None:
        self._page = page
        self._page_ws = page_ws

    async def get_page_by_id(self, page_id: UUID, workspace_id: UUID | None = None):
        if page_id != self._page.page_id:
            return None
        if workspace_id is not None and workspace_id != self._page_ws:
            return None
        return self._page


def _page(page_id: UUID, artifact_id: UUID) -> SimpleNamespace:
    return SimpleNamespace(
        page_id=page_id,
        artifact_id=artifact_id,
        index=0,
        name="secret",
        text_mention=SimpleNamespace(text="confidential body"),
    )


@pytest.mark.asyncio
async def test_foreign_workspace_page_not_returned_to_full_access_member() -> None:
    victim_ws, attacker_ws = uuid4(), uuid4()
    pid, aid = uuid4(), uuid4()
    tool = GetPageContentTool(_WorkspaceScopedPages(_page(pid, aid), page_ws=victim_ws))

    # Full-access member (allowed_artifact_ids=None) in a DIFFERENT workspace.
    results, summary, _ = await tool.execute(
        {"page_id": str(pid)}, workspace_id=attacker_ws, allowed_artifact_ids=None
    )

    assert results == []
    assert "not found" in summary
    assert "confidential" not in summary


@pytest.mark.asyncio
async def test_own_workspace_page_is_returned() -> None:
    ws = uuid4()
    pid, aid = uuid4(), uuid4()
    tool = GetPageContentTool(_WorkspaceScopedPages(_page(pid, aid), page_ws=ws))

    results, _, _ = await tool.execute(
        {"page_id": str(pid)}, workspace_id=ws, allowed_artifact_ids=None
    )

    assert len(results) == 1
    assert results[0].expanded_text == "confidential body"
