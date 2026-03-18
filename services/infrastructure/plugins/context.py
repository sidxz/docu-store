"""PluginContext implementation — narrow facade over core services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DefaultPluginContext:
    """Concrete PluginContext provided to plugins at runtime.

    Exposes read models, shared utilities, and a MongoDB handle for
    plugin-owned collections.  Never exposes aggregate repositories
    or the core workflow orchestrator.
    """

    page_read_model: Any
    artifact_read_model: Any
    smiles_validator: Any
    embedding_generator: Any
    mongo_db: Any  # AsyncIOMotorDatabase
    temporal_client: Any  # temporalio.client.Client
    plugin_config: dict[str, Any]
