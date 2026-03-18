"""PubChem plugin manifest."""

from application.plugins.manifest import PluginManifest

PUBCHEM_MANIFEST = PluginManifest(
    name="pubchem_enrichment",
    version="1.0.0",
    description="Enriches extracted compounds with PubChem CID, IUPAC name, molecular formula, and more.",
    subscribed_events=["CompoundMentionsUpdated", "ArtifactDeleted", "PageDeleted"],
    consumer_group="plugin_pubchem",
    mongo_collections=["pubchem_enrichments"],
    temporal_task_queue="plugin_pubchem",
    has_api_routes=True,
    api_prefix="/plugins/pubchem",
)
