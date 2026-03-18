"""Plugin discovery and loading from the ENABLED_PLUGINS config."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import structlog

from application.plugins.registry import PluginRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from application.plugins.protocol import Plugin

logger = structlog.get_logger()


def discover_plugins(
    enabled_plugins: list[str],
    plugin_dir: Path,
) -> PluginRegistry:
    """Load enabled plugins and return a populated registry.

    Each plugin is expected to be a Python package inside *plugin_dir*
    that exports a ``plugin`` attribute implementing the ``Plugin`` protocol.

    Args:
        enabled_plugins: List of plugin package names to load.
        plugin_dir: Root directory containing plugin packages.

    Returns:
        A PluginRegistry with all successfully loaded plugins.

    """
    registry = PluginRegistry()

    if not enabled_plugins:
        logger.info("plugin_loader.no_plugins_enabled")
        return registry

    for name in enabled_plugins:
        try:
            plugin_path = plugin_dir / name
            if not plugin_path.is_dir():
                logger.warning(
                    "plugin_loader.directory_not_found",
                    plugin=name,
                    path=str(plugin_path),
                )
                continue

            module = importlib.import_module(f"plugins.{name}")
            plugin_obj: Plugin = getattr(module, "plugin", None)  # type: ignore[assignment]

            if plugin_obj is None:
                logger.warning("plugin_loader.no_plugin_attribute", plugin=name)
                continue

            registry.register(plugin_obj)
            logger.info("plugin_loader.loaded", plugin=name)

        except Exception:
            logger.exception("plugin_loader.load_failed", plugin=name)

    logger.info("plugin_loader.complete", loaded=len(registry), requested=len(enabled_plugins))
    return registry
