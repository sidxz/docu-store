"""Plugin protocol and supporting interfaces."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import APIRouter

    from application.plugins.manifest import PluginManifest


class PluginContext(Protocol):
    """Narrow, read-only facade over core services provided to plugins.

    Plugins receive this instead of the full DI container.  It exposes
    read models (projected state) and shared stateless utilities — never
    aggregate repositories or the core workflow orchestrator.
    """

    @property
    def page_read_model(self) -> Any:  # noqa: ANN401
        """MongoDB page read-model accessor."""
        ...

    @property
    def artifact_read_model(self) -> Any:  # noqa: ANN401
        """MongoDB artifact read-model accessor."""
        ...

    @property
    def smiles_validator(self) -> Any:  # noqa: ANN401
        """Stateless SMILES validation utility."""
        ...

    @property
    def embedding_generator(self) -> Any:  # noqa: ANN401
        """Shared embedding generator."""
        ...

    @property
    def mongo_db(self) -> Any:  # noqa: ANN401
        """AsyncIOMotorDatabase for plugin-owned collections."""
        ...

    @property
    def temporal_client(self) -> Any:  # noqa: ANN401
        """Temporal client for starting plugin workflows."""
        ...

    @property
    def plugin_config(self) -> dict[str, Any]:
        """Plugin-specific configuration parsed from env."""
        ...


class PluginEventHandler(Protocol):
    """Handles a Kafka message for a plugin — typically starts a Temporal workflow."""

    @property
    def plugin_name(self) -> str:
        """Name of the owning plugin."""
        ...

    async def handle(self, event_type: str, sub_type: str, data: dict[str, Any]) -> None:
        """Process an event delivered via Kafka.

        Args:
            event_type: Coarse event type (e.g. "PageUpdated").
            sub_type: Fine-grained sub-type (e.g. "CompoundMentionsUpdated").
            data: Full DTO payload from the Kafka message.

        """
        ...


@runtime_checkable
class Plugin(Protocol):
    """Interface every plugin must implement."""

    @staticmethod
    def manifest() -> PluginManifest:
        """Return the plugin's declarative manifest."""
        ...

    def create_event_handler(self, context: PluginContext) -> PluginEventHandler:
        """Return the handler that processes subscribed events."""
        ...

    def create_workflows(self) -> list[type]:
        """Return Temporal workflow classes to register."""
        ...

    def create_activities(self, context: PluginContext) -> list[Callable[..., Any]]:
        """Return Temporal activity callables."""
        ...

    def create_router(self, context: PluginContext) -> APIRouter | None:
        """Return a FastAPI router for plugin-specific endpoints, or None."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Return plugin health status."""
        ...

    async def backfill(self, context: PluginContext) -> None:
        """Backfill enrichment data from read models for historical records."""
        ...
