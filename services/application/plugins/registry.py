"""Plugin registry — discovers, validates, and manages plugin lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from application.plugins.manifest import PluginManifest
    from application.plugins.protocol import Plugin, PluginContext, PluginEventHandler

logger = structlog.get_logger()


class PluginRegistry:
    """Holds all registered plugins and builds event routing tables."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._manifests: dict[str, PluginManifest] = {}

    def register(self, plugin: Plugin) -> None:
        """Register a plugin after validating its manifest."""
        manifest = plugin.manifest()
        if manifest.name in self._plugins:
            msg = f"Duplicate plugin name: {manifest.name}"
            raise ValueError(msg)

        self._plugins[manifest.name] = plugin
        self._manifests[manifest.name] = manifest
        logger.info(
            "plugin_registered",
            name=manifest.name,
            version=manifest.version,
            subscribed_events=manifest.subscribed_events,
        )

    def get_plugin(self, name: str) -> Plugin:
        """Get a plugin by name."""
        return self._plugins[name]

    def get_manifest(self, name: str) -> PluginManifest:
        """Get a plugin manifest by name."""
        return self._manifests[name]

    def list_manifests(self) -> list[PluginManifest]:
        """Return all registered plugin manifests."""
        return list(self._manifests.values())

    def list_names(self) -> list[str]:
        """Return all registered plugin names."""
        return list(self._plugins.keys())

    def build_event_routing_table(
        self,
        context: PluginContext,
    ) -> dict[str, list[PluginEventHandler]]:
        """Build a mapping of sub_type → list of plugin event handlers.

        Args:
            context: PluginContext to pass to each plugin's create_event_handler.

        Returns:
            Dict mapping Kafka sub_type strings to lists of handlers.

        """
        table: dict[str, list[PluginEventHandler]] = {}
        for name, plugin in self._plugins.items():
            manifest = self._manifests[name]
            handler = plugin.create_event_handler(context)
            for sub_type in manifest.subscribed_events:
                table.setdefault(sub_type, []).append(handler)
        return table

    def collect_all_subscribed_events(self) -> set[str]:
        """Return the union of all subscribed event sub-types."""
        events: set[str] = set()
        for manifest in self._manifests.values():
            events.update(manifest.subscribed_events)
        return events

    def collect_workflows(self) -> list[type]:
        """Collect all Temporal workflow classes from all plugins."""
        workflows: list[type] = []
        for plugin in self._plugins.values():
            workflows.extend(plugin.create_workflows())
        return workflows

    def collect_activities(self, context: PluginContext) -> list[Any]:
        """Collect all Temporal activity callables from all plugins."""
        activities: list[Any] = []
        for plugin in self._plugins.values():
            activities.extend(plugin.create_activities(context))
        return activities

    def __len__(self) -> int:
        return len(self._plugins)
