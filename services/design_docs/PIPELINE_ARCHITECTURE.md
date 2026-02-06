"""
# Long-Running Pipeline Architecture

## Overview

This module implements a clean architecture for running long-running artifact processing pipelines using Temporal for orchestration. The design separates concerns across layers while maintaining testability and domain purity.

## Architecture Layers

### 1. Domain Layer (Pure Business Logic)
- **Location**: `domain/`
- **Responsibility**: Define what processing is needed, not how
- **Independence**: Knows nothing about Temporal, Kafka, or specific frameworks
- **Example**: Artifact aggregate, domain events, value objects

### 2. Application Layer (Use Cases & Ports)
- **Location**: `application/`
- **Responsibility**: Orchestration of domain and infrastructure
- **Ports**: Abstract interfaces that define what infrastructure must provide
- **Key Port**: `PipelineOrchestrator` - abstraction for starting pipelines

```python
class PipelineOrchestrator(ABC):
    async def start_artifact_processing_pipeline(
        self, 
        artifact_id: UUID, 
        storage_location: str
    ) -> None:
        """Start a long-running pipeline for an artifact"""
```

**Advantage**: Application doesn't know if we're using Temporal, Celery, Step Functions, etc.

### 3. Infrastructure Layer (Implementations)
- **Location**: `infrastructure/`
- **Responsibility**: Implement ports with specific technologies

#### 3a. Event Subscription (pipeline_worker.py)
```
EventStoreDB (source of truth)
    └─ ApplicationSubscription (from eventsourcing)
        └─ Listen for ArtifactCreated events
            └─ Call PipelineOrchestrator.start_artifact_processing_pipeline()
```

#### 3b. Temporal Workflow Orchestration
```
infrastructure/temporal/
├── orchestrator.py          # Implements PipelineOrchestrator port
├── worker.py                # Temporal worker process (executes workflows)
├── workflows/
│   └── artifact_processing.py   # Workflow definition (toy example)
└── activities/
    └── artifact_activities.py   # Activity implementations
```

## Event Flow

```
1. User uploads artifact
   └─ API → ArtifactUploadSaga → CreateArtifactUseCase
      └─ Saves Artifact aggregate to EventStoreDB
      └─ Emits ArtifactCreated event

2. Event Subscription (pipeline_worker.py)
   └─ Receives ArtifactCreated event from EventStoreDB
   └─ Calls orchestrator.start_artifact_processing_pipeline()

3. Temporal Orchestration (TemporalPipelineOrchestrator)
   └─ Starts ProcessArtifactPipeline workflow
   └─ Workflow ID = artifact_id (ensures idempotency)

4. Temporal Workflow Execution
   └─ log_mime_type_activity (toy - will be PDF parsing)
   └─ log_storage_location_activity (toy - will be page extraction)
   └─ [Future: LLM summarization, etc.]

5. Results Persisted (future)
   └─ Activity calls UpdateSummaryCandidateUseCase
   └─ Use case saves events to EventStoreDB
   └─ Events propagate to read models and external subscribers
```

## Running the System

### 1. Start Temporal Server (docker-compose)
```bash
docker-compose up temporal postgres temporal-ui
```

### 2. Start Temporal Worker (processes workflows/activities)
```bash
python -m infrastructure.temporal.worker
```

### 3. Start Pipeline Worker (listens to events, triggers workflows)
```bash
python infrastructure/pipeline_worker.py
```

### 4. Start your API server
```bash
python main.py  # Or your existing API startup
```

### 5. Create an artifact (triggers the pipeline!)
```bash
# POST /artifacts with a file
# This creates ArtifactCreated event
# → pipeline_worker detects it
# → starts Temporal workflow
# → workflow runs activities
# → results appear in Temporal UI
```

## Key Design Principles

### 1. Separation of Concerns
- **Domain**: What to do (pure business logic)
- **Application**: When to do it (use cases, orchestration)
- **Infrastructure**: How to do it (Temporal, databases, etc.)

### 2. Dependency Inversion
```
Domain → Application ← Infrastructure

Application depends on ports (abstractions)
Infrastructure implements ports (concrete)
```

### 3. Event Sourcing as Integration Point
- Single source of truth: EventStoreDB
- Both read_worker and pipeline_worker subscribe to same event stream
- No direct coupling between components

### 4. Idempotency
- Workflow ID = artifact_id ensures same artifact never processed twice
- Safe to replay events without duplicates

### 5. Observability
- Temporal UI shows all workflow executions and state
- Structured logging throughout pipeline
- Event history in EventStoreDB for audit trail

## Expanding the Pipeline

### Add a New Activity (Example: PDF Parsing)

**1. Define Activity** (`infrastructure/temporal/activities/artifact_activities.py`)
```python
@activity.defn
async def parse_pdf_activity(storage_location: str) -> dict:
    """Extract text from PDF"""
    logger.info("activity_parsing_pdf", location=storage_location)
    # Real implementation would use PyPDF2, pdfplumber, etc.
    return {"text": "...extracted PDF text..."}
```

**2. Add to Workflow** (`infrastructure/temporal/workflows/artifact_processing.py`)
```python
pdf_data = await workflow.execute_activity(
    parse_pdf_activity,
    storage_location,
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=3),
)
```

**3. Register in Worker** (`infrastructure/temporal/worker.py`)
```python
worker = Worker(
    client,
    task_queue="artifact_processing",
    workflows=[ProcessArtifactPipeline],
    activities=[
        log_mime_type_activity,
        log_storage_location_activity,
        parse_pdf_activity,  # Add here
        # ... more activities
    ],
)
```

### Persist Results Back to Domain

**Future Activity Pattern**:
```python
@activity.defn
async def update_artifact_activity(
    artifact_id: UUID,
    summary: str,
    container: Container,  # Get from context
):
    """Update artifact with processing results"""
    use_case = container[UpdateSummaryCandidateUseCase]
    await use_case.execute(
        artifact_id=artifact_id,
        summary=SummaryCandidate(text=summary, source="llm")
    )
    # Domain event emitted → read models updated
```

## Testing Strategy

### 1. Unit Test Domain Logic (no Temporal needed)
```python
def test_artifact_creation():
    artifact = Artifact.create(...)
    assert artifact.id is not None
    # Pure business logic, no infrastructure
```

### 2. Unit Test Use Cases
```python
async def test_create_artifact_use_case():
    repo = MockArtifactRepository()
    use_case = CreateArtifactUseCase(repo)
    result = await use_case.execute(request)
    # Mock repository, no real database
```

### 3. Unit Test Activities (mock external dependencies)
```python
async def test_parse_pdf_activity():
    # Mock blob store
    with mock.patch("blob_store.get") as mock_get:
        mock_get.return_value = "PDF content"
        result = await parse_pdf_activity("path/to/file.pdf")
        assert "text" in result
```

### 4. Integration Test Temporal Workflows
```python
async def test_artifact_pipeline_workflow():
    # Use Temporal test client
    async with WorkflowEnvironment.start_time_skipping() as env:
        client = await env.client
        worker = Worker(client, ...)
        
        # Run workflow to completion in test
        await client.start_workflow(
            ProcessArtifactPipeline.execute,
            args=[artifact_id, location, mime_type],
            id="test-workflow",
            task_queue="test",
        )
```

## Deployment Considerations

### Single Machine Development
```
One Temporal server (docker-compose)
One pipeline worker
One API server
```

### Production Deployment
```
Multiple Temporal servers (cluster)
Multiple pipeline workers (scale independently)
Load balancer for API servers
Monitoring/alerting on workflow failures
```

### Configuration
- `settings.temporal_address`: Where Temporal server is running
- Worker task queue: "artifact_processing" (configurable)
- Retry policies: Configurable per activity
- Timeouts: Configurable per activity

## References

- Temporal Python SDK: https://docs.temporal.io/develop/python/
- EventSourcing patterns: https://eventsourcing.readthedocs.io/
- Domain-Driven Design: Evans, "Domain-Driven Design"
- Clean Architecture: Martin, "Clean Architecture"
"""
