"""Declarative contract for a plugin."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """Declares what a plugin needs and provides.

    Every plugin must expose a manifest so the plugin system knows which
    Kafka sub-types to route, which MongoDB collections to expect, and
    whether the plugin adds API routes.
    """

    name: str = Field(..., description="Unique plugin identifier, e.g. 'pubchem_enrichment'")
    version: str = Field(..., description="Semver version string")
    description: str = Field(default="", description="Human-readable description")

    # Events
    subscribed_events: list[str] = Field(
        default_factory=list,
        description="Kafka sub_type values this plugin reacts to, e.g. ['CompoundMentionsUpdated']",
    )

    # Kafka
    consumer_group: str | None = Field(
        default=None,
        description="Kafka consumer group. Defaults to 'plugin_{name}'.",
    )

    # Storage
    mongo_collections: list[str] = Field(
        default_factory=list,
        description="MongoDB collection names owned by this plugin.",
    )

    # Temporal
    temporal_task_queue: str | None = Field(
        default=None,
        description="Temporal task queue. Defaults to 'plugin_{name}'.",
    )

    # API
    has_api_routes: bool = Field(
        default=False,
        description="Whether this plugin adds FastAPI routes.",
    )
    api_prefix: str | None = Field(
        default=None,
        description="Route prefix, e.g. '/plugins/pubchem'.",
    )

    def effective_consumer_group(self) -> str:
        """Return consumer group, falling back to 'plugin_{name}'."""
        return self.consumer_group or f"plugin_{self.name}"

    def effective_task_queue(self) -> str:
        """Return Temporal task queue, falling back to 'plugin_{name}'."""
        return self.temporal_task_queue or f"plugin_{self.name}"
