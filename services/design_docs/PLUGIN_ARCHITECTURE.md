# Plugin Architecture

## Why Plugins?

Adding a new ML/external service the traditional way (see `ADDING_SERVICES.md`) requires modifying **7 core files**: workflow_orchestrator port, temporal orchestrator, temporal worker, DI container, pipeline_worker, plus new use case + workflow. This violates the Open/Closed Principle.

The plugin system lets you add external capabilities that react to domain events, do work, and store results — **without touching core code**.

**Use the plugin system when:**
- You need to enrich domain data with external APIs (PubChem, ChEMBL, UniProt)
- The enrichment is supplementary — not part of the core domain model
- You want isolated storage, independent failure handling, and easy enable/disable

**Use the traditional approach (`ADDING_SERVICES.md`) when:**
- The service produces core domain data (e.g., compound extraction, NER)
- The result is stored on the domain aggregate itself
- The service is part of the core event pipeline sequencing

---

## Architecture Overview

```
EventStoreDB
  ├── read_worker           → MongoDB projections (existing)
  ├── pipeline_worker       → core Temporal workflows (existing)
  │     ↓ (use cases publish to Kafka with sub_type after domain operations)
  │
Kafka topic: docu_store_events (enhanced with sub-types)
  ├── Existing consumers    (see coarse PageUpdated/ArtifactUpdated)
  ├── Consumer Group: plugin_pubchem   → PubChem plugin → Temporal workflow
  ├── Consumer Group: plugin_chembl    → ChEMBL plugin → Temporal workflow
  └── ...
```

### How Events Reach Plugins

1. A core use case modifies a domain aggregate (e.g., compounds extracted)
2. The use case calls `ExternalEventPublisher.notify_page_updated(result, sub_type="CompoundMentionsUpdated")`
3. `KafkaExternalEventPublisher` publishes to Kafka with the sub_type in the message
4. The plugin consumer process receives the message, matches sub_type against plugin manifests
5. The matching plugin handler starts a Temporal workflow on the plugin's task queue

### Kafka Message Format

```json
{
  "event_type": "PageUpdated",
  "sub_type": "CompoundMentionsUpdated",
  "data": { "page_id": "...", "artifact_id": "...", "compound_mentions": [...], ... }
}
```

The `data` field contains the full `PageResponse` or `ArtifactResponse` DTO — plugins get rich context without needing to query read models.

### Available Sub-Types

| Sub-Type | Emitted By | Triggered When |
|----------|-----------|---------------|
| `CompoundMentionsUpdated` | `ExtractCompoundMentionsUseCase`, `AddCompoundMentionsUseCase` | Compounds extracted or manually added |
| `TextMentionUpdated` | `UpdateTextMentionUseCase` | Page text extracted from PDF |
| `TagMentionsUpdated` | `UpdateTagMentionsUseCase`, `ExtractPageEntitiesUseCase` | NER entities extracted |
| `SummaryCandidateUpdated` | `SummarizePageUseCase`, `UpdateSummaryCandidateUseCase`, `SummarizeArtifactUseCase` | LLM summary generated |
| `PagesAdded` | `AddPagesUseCase` | Pages linked to artifact |
| `PagesRemoved` | `RemovePagesUseCase` | Pages unlinked from artifact |
| `TitleMentionUpdated` | `UpdateTitleMentionUseCase` | Artifact title extracted |
| `TagsUpdated` | `UpdateTagsUseCase`, `AggregateArtifactTagsUseCase` | Artifact tags aggregated |

---

## Where Plugins Sit in Clean Architecture

```
Domain Layer         — UNTOUCHED. Plugins never modify aggregates.
                       Domain events are the plugin's public API.

Application Layer    — Plugin contracts live here:
                         application/plugins/manifest.py   (PluginManifest)
                         application/plugins/protocol.py   (Plugin, PluginEventHandler, PluginContext)
                         application/plugins/registry.py   (PluginRegistry)

Infrastructure Layer — Plugin machinery lives here:
                         infrastructure/plugins/loader.py           (discovery)
                         infrastructure/plugins/context.py          (PluginContext impl)
                         infrastructure/plugins/plugin_consumer.py  (Kafka consumer)

Interface Layer      — main.py mounts plugin API routers dynamically.
                       GET /plugins returns all enabled plugin manifests.

Plugin Packages      — plugins/<name>/  (in-repo, each is a self-contained package)
```

---

## Plugin Contract

### PluginManifest

Every plugin declares what it needs and provides via a `PluginManifest`:

```python
from application.plugins.manifest import PluginManifest

MY_MANIFEST = PluginManifest(
    name="my_plugin",                              # Unique identifier
    version="1.0.0",                               # Semver
    description="What this plugin does.",
    subscribed_events=["CompoundMentionsUpdated"],  # Kafka sub_types to react to
    consumer_group="plugin_my_plugin",              # Kafka consumer group (default: plugin_{name})
    mongo_collections=["my_plugin_data"],           # Plugin-owned MongoDB collections
    temporal_task_queue="plugin_my_plugin",          # Temporal task queue (default: plugin_{name})
    has_api_routes=True,                            # Whether plugin adds FastAPI routes
    api_prefix="/plugins/my_plugin",                # Route prefix
)
```

### Plugin Protocol

Every plugin must implement this interface:

```python
class MyPlugin:
    @staticmethod
    def manifest() -> PluginManifest:
        return MY_MANIFEST

    def create_event_handler(self, context: PluginContext) -> PluginEventHandler:
        """Return a handler that receives Kafka events and starts Temporal workflows."""
        ...

    def create_workflows(self) -> list[type]:
        """Return Temporal @workflow.defn classes."""
        ...

    def create_activities(self, context: PluginContext) -> list[Callable]:
        """Return Temporal @activity.defn callables."""
        ...

    def create_router(self, context: PluginContext) -> APIRouter | None:
        """Return a FastAPI router, or None."""
        ...

    async def health_check(self) -> dict[str, Any]:
        """Return plugin health status."""
        ...

    async def backfill(self, context: PluginContext) -> None:
        """Backfill enrichment data from read models for historical records."""
        ...
```

### PluginContext

Plugins receive a narrow, read-only facade — **not** the full DI container:

| Provided | NOT Provided |
|----------|-------------|
| `page_read_model` — MongoDB page queries | `PageRepository` — event-sourced aggregate |
| `artifact_read_model` — MongoDB artifact queries | `ArtifactRepository` — event-sourced aggregate |
| `smiles_validator` — stateless utility | Core Qdrant stores |
| `embedding_generator` — shared | `WorkflowOrchestrator` — core port |
| `mongo_db` — for plugin's own collections | `ExternalEventPublisher` |
| `temporal_client` — for plugin's own workflows | |
| `plugin_config` — parsed from env | |

**Key boundary:** Plugins get **read models** (projected state), not **repositories** (aggregate access). Plugins can never load or save domain aggregates.

---

## Plugin Storage

Plugins own their own MongoDB collections. They **cannot**:
- Write to `page_read_models` or `artifact_read_models`
- Modify existing Qdrant collection payloads
- Modify domain aggregates

If a plugin needs vector search, it creates its own Qdrant collection.

---

## Plugin Execution

Every plugin handler starts a Temporal workflow (never runs inline):
- **Reliability** — external APIs fail; Temporal retries automatically
- **Isolation** — plugin workflows run on separate task queues
- **Observability** — every execution visible in Temporal UI
- **Consistency** — same pattern as all core services

---

## Configuration

### Enable plugins

In `.env`:
```
ENABLED_PLUGINS=pubchem_enrichment,my_other_plugin
```

### Per-plugin config

Each plugin defines its own Settings with a `PLUGIN_{NAME}_` prefix:
```
PLUGIN_PUBCHEM_API_BASE_URL=https://pubchem.ncbi.nlm.nih.gov/rest/pug
PLUGIN_PUBCHEM_RATE_LIMIT_PER_SECOND=5.0
PLUGIN_PUBCHEM_BATCH_SIZE=10
```

---

## Developing a Plugin — Step by Step

Use `plugins/pubchem_enrichment/` as the reference implementation.

### 1. Create the directory structure

```
plugins/my_plugin/
  __init__.py          # Exports `plugin` attribute
  manifest.py          # PluginManifest
  config.py            # Plugin-specific pydantic Settings
  plugin.py            # Main Plugin class
  use_cases/
    __init__.py
    my_logic.py        # Core business logic
  infrastructure/
    __init__.py
    my_client.py       # External API client
  storage/
    __init__.py
    my_store.py        # MongoDB adapter
  temporal/
    __init__.py
    workflows.py       # @workflow.defn
    activities.py      # @activity.defn factory
  api/
    __init__.py
    routes.py          # FastAPI router
```

### 2. Define the manifest

```python
# plugins/my_plugin/manifest.py
from application.plugins.manifest import PluginManifest

MY_MANIFEST = PluginManifest(
    name="my_plugin",
    version="1.0.0",
    description="Enriches pages with data from MyService.",
    subscribed_events=["CompoundMentionsUpdated"],
    mongo_collections=["my_plugin_enrichments"],
    has_api_routes=True,
    api_prefix="/plugins/my_plugin",
)
```

### 3. Build the external API client

```python
# plugins/my_plugin/infrastructure/my_client.py
class MyServiceClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url
        self._timeout = timeout

    async def lookup(self, query: str) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self.base_url}/search?q={query}")
            response.raise_for_status()
            return response.json()
```

### 4. Build the storage adapter

```python
# plugins/my_plugin/storage/my_store.py
class MyPluginStore:
    def __init__(self, mongo_db):
        self._collection = mongo_db["my_plugin_enrichments"]

    async def ensure_indexes(self):
        await self._collection.create_index("page_id")

    async def upsert(self, page_id, data):
        await self._collection.update_one(
            {"page_id": str(page_id)},
            {"$set": data},
            upsert=True,
        )

    async def get_for_page(self, page_id):
        cursor = self._collection.find({"page_id": str(page_id)}, {"_id": 0})
        return await cursor.to_list(length=None)
```

### 5. Write the core use case

```python
# plugins/my_plugin/use_cases/my_logic.py
async def enrich_page(page_data: dict, client: MyServiceClient, store: MyPluginStore) -> dict:
    page_id = page_data["page_id"]
    # Extract what you need from the full PageResponse DTO
    compounds = page_data.get("compound_mentions", [])
    for compound in compounds:
        result = await client.lookup(compound["canonical_smiles"])
        await store.upsert(page_id, result)
    return {"page_id": page_id, "enriched": len(compounds)}
```

### 6. Create the Temporal workflow + activity

```python
# plugins/my_plugin/temporal/workflows.py
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class MyPluginWorkflow:
    @workflow.run
    async def run(self, page_data_json: str) -> dict:
        return await workflow.execute_activity(
            "my_plugin_enrich",
            page_data_json,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=workflow.RetryPolicy(maximum_attempts=3),
        )
```

```python
# plugins/my_plugin/temporal/activities.py
import json
from temporalio import activity

def create_enrich_activity(mongo_db):
    client = MyServiceClient(base_url="https://api.example.com")
    store = MyPluginStore(mongo_db)

    @activity.defn(name="my_plugin_enrich")
    async def my_plugin_enrich(page_data_json: str) -> dict:
        page_data = json.loads(page_data_json)
        return await enrich_page(page_data, client, store)

    return my_plugin_enrich
```

### 7. Create the event handler

```python
# In plugin.py
class MyPluginEventHandler:
    def __init__(self, temporal_client, task_queue: str):
        self._temporal_client = temporal_client
        self._task_queue = task_queue

    @property
    def plugin_name(self) -> str:
        return "my_plugin"

    async def handle(self, event_type: str, sub_type: str, data: dict) -> None:
        page_id = data.get("page_id", "unknown")
        await self._temporal_client.start_workflow(
            "MyPluginWorkflow",
            json.dumps(data),
            id=f"my-plugin-{page_id}",
            task_queue=self._task_queue,
        )
```

### 8. Add API routes

```python
# plugins/my_plugin/api/routes.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/pages/{page_id}/enrichments")
async def get_enrichments(page_id: UUID):
    store = MyPluginStore(get_mongo_db())
    return await store.get_for_page(page_id)

@router.get("/status")
async def status():
    return {"plugin": "my_plugin", "status": "healthy"}
```

### 9. Wire it all together

```python
# plugins/my_plugin/plugin.py
class MyPlugin:
    @staticmethod
    def manifest():
        return MY_MANIFEST

    def create_event_handler(self, context):
        return MyPluginEventHandler(context.temporal_client, MY_MANIFEST.effective_task_queue())

    def create_workflows(self):
        return [MyPluginWorkflow]

    def create_activities(self, context):
        return [create_enrich_activity(context.mongo_db)]

    def create_router(self, context):
        return router

    async def health_check(self):
        return {"plugin": "my_plugin", "status": "healthy"}

    async def backfill(self, context):
        pass  # Implement if needed
```

### 10. Export the plugin

```python
# plugins/my_plugin/__init__.py
from plugins.my_plugin.plugin import MyPlugin
plugin = MyPlugin()
```

### 11. Enable it

Add to `.env`:
```
ENABLED_PLUGINS=pubchem_enrichment,my_plugin
```

---

## Backfill

When a plugin is installed after documents have already been processed:

1. **Automatic (Kafka replay):** New consumer groups start from `auto.offset.reset=earliest`, replaying all events within Kafka's retention window.
2. **Manual:** Call the plugin's `backfill()` method, which iterates MongoDB read models and runs the enrichment logic directly.

---

## Frontend Integration

Core API endpoints (`GET /pages/{page_id}`) return core data only.  Plugin data is fetched separately:

1. `GET /plugins` — discover enabled plugins and their manifests
2. `GET /plugins/{name}/pages/{page_id}/enrichments` — fetch plugin data
3. Join client-side on `canonical_smiles`, `page_id`, etc.

This keeps the core API stable — adding or removing a plugin never changes core response shapes.

---

## File Reference

| Component | Location | Purpose |
|-----------|----------|---------|
| PluginManifest | `application/plugins/manifest.py` | Declarative plugin contract |
| Plugin Protocol | `application/plugins/protocol.py` | Plugin, PluginEventHandler, PluginContext interfaces |
| PluginRegistry | `application/plugins/registry.py` | Discovery, validation, event routing |
| Plugin Loader | `infrastructure/plugins/loader.py` | Reads ENABLED_PLUGINS, imports packages |
| PluginContext | `infrastructure/plugins/context.py` | Narrow facade over core services |
| Plugin Consumer | `infrastructure/plugins/plugin_consumer.py` | Kafka consumer + Temporal worker |
| Reference Plugin | `plugins/pubchem_enrichment/` | Complete working example |

---

## Checklist — New Plugin

- [ ] `plugins/<name>/` — directory with `__init__.py` exporting `plugin`
- [ ] `manifest.py` — PluginManifest with subscribed events, collections, routes
- [ ] `config.py` — pydantic Settings with `PLUGIN_{NAME}_` prefix
- [ ] `plugin.py` — Plugin class implementing the protocol
- [ ] `infrastructure/<client>.py` — external API client
- [ ] `storage/<store>.py` — MongoDB adapter for plugin-owned collection
- [ ] `temporal/workflows.py` — Temporal workflow
- [ ] `temporal/activities.py` — activity factory with injected dependencies
- [ ] `api/routes.py` — FastAPI router (if `has_api_routes=True`)
- [ ] `.env` — add plugin name to `ENABLED_PLUGINS`
- [ ] `.env` — add any `PLUGIN_{NAME}_*` config vars
- [ ] Verify: `uv run python -c "from plugins.<name> import plugin; print(plugin.manifest())"`
