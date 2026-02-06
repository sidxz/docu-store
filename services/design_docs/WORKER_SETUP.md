## Read Worker Setup Summary

You have a minimal, straightforward read model projection system with proper DI wiring.

### Architecture

**1. DI Container** (`infrastructure/di/container.py`)
- Registers `DocuStoreApplication` (custom Application subclass for Pydantic transcodings)
- Registers `MongoReadModelMaterializer` (MongoDB read model operations)
- Registers `EventProjector` (routes events to handlers)

**2. Event Projector** (`infrastructure/event_projectors/event_projector.py`)
- Simple event-to-handler mapping (no unnecessary abstraction)
- Maps event types to their projection methods
- Exposes `materializer` property for tracking and state management
- Exposes `topics` property for subscription filtering

```python
# How it works internally:
self._handlers = {
    Page.Created: page_projector.page_created,
    Page.CompoundMentionsUpdated: page_projector.compound_mentions_updated,
}
```

**3. Page Projector** (`infrastructure/event_projectors/page_projector.py`)
- `page_created()` → inserts page read model with empty compound_mentions list
- `compound_mentions_updated()` → updates compound_mentions using `.model_dump(mode="json")`
- Receives Pydantic models from events and serializes them for storage

**4. Read Worker** (`infrastructure/di/read_worker.py`)
- Gets `EventProjector` from DI container
- Creates ApplicationSubscription with event topics
- Processes each event via `event_projector.process_event()`
- Handles idempotency with IntegrityError (skips already-processed events)
- Graceful shutdown via signal handlers

### How to Run

```bash
python infrastructure/di/read_worker.py
```

This will:
- Subscribe to Page.Created and Page.CompoundMentionsUpdated events from KurrentDB
- Materialize them to MongoDB read models
- Track processed events to prevent reprocessing
- Handle graceful shutdown on SIGINT/SIGTERM

### Adding New Projectors

To add a new projector (e.g., ArticleProjector):

1. Create the projector class: `infrastructure/event_projectors/article_projector.py`
2. Update `EventProjector._handlers` dict:

```python
article_projector = ArticleProjector(materializer)
self._handlers.update({
    Article.Created: article_projector.article_created,
    Article.Updated: article_projector.article_updated,
})
```

3. The worker automatically picks up new event types from `topics` property
