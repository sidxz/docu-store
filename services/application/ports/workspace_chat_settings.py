"""Chat behaviour a workspace admin switches for the whole workspace.

Unset → the server default (``CHAT_ENABLE_ANSWER_FORMATTING``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID


class WorkspaceChatSettingsStore(Protocol):
    async def get_answer_formatting(self, workspace_id: UUID) -> bool | None: ...

    async def set_answer_formatting(
        self, workspace_id: UUID, on: bool, *, updated_by: UUID
    ) -> None: ...
