from abc import ABC, abstractmethod
from uuid import UUID

from application.dtos.user_dtos import TermsAcceptanceDTO


class TermsAcceptanceStore(ABC):
    """Record of which Terms/Privacy version each user accepted, and when.

    NOT event-sourced, and deliberately not part of user preferences: this is an
    audit record, so it is append-only from the client's point of view (there is
    no update path exposed over the API) and keyed by user alone. A user who
    belongs to several workspaces accepts once, not once per workspace.
    """

    @abstractmethod
    async def get_acceptance(self, user_id: UUID) -> TermsAcceptanceDTO | None:
        """The user's most recent acceptance, or None if they never accepted."""

    @abstractmethod
    async def record_acceptance(self, user_id: UUID, version: str) -> TermsAcceptanceDTO:
        """Record acceptance of ``version``. Idempotent per (user, version)."""

    @abstractmethod
    async def ensure_indexes(self) -> None:
        pass
