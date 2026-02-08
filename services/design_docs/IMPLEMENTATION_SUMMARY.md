# Implementation Summary

## Files Created

This implementation creates a clean, extensible architecture for long-running artifact processing pipelines using Temporal.

### 1. Application Layer (Domain-Independent)

**`application/ports/pipeline_orchestrator.py`** (NEW)
- Abstract port defining the orchestration interface
- Domain and application layers depend only on this abstraction
- Can swap Temporal for Celery/Step Functions without changing application code

```python
class WorkflowOrchestrator(ABC):
    async def start_artifact_processing_workflow(
        self, 
        artifact_id: UUID, 
        storage_location: str
    ) -> None: ...
```

### 2. Infrastructure Layer

#### 2.1 Temporal Workflow & Activities

**`infrastructure/temporal/__init__.py`** (NEW)
- Package marker for Temporal infrastructure

**`infrastructure/temporal/workflows/__init__.py`** (NEW)
- Package marker for workflows

**`infrastructure/temporal/workflows/artifact_processing.py`** (NEW)
- `ProcessArtifactWorkflow` workflow class
- Orchestrates the processing steps
- Handles retries, timeouts, error handling
- Currently runs toy activities (logging)
- Framework: Durable, observable, idempotent by design

```python
@workflow.defn
class ProcessArtifactWorkflow:
    @workflow.run
    async def execute(
        self,
        artifact_id: UUID,
        storage_location: str,
        mime_type: str,
    ) -> str: ...
```

**`infrastructure/temporal/activities/__init__.py`** (NEW)
- Package marker for activities

**`infrastructure/temporal/activities/artifact_activities.py`** (NEW)
- `log_mime_type_activity`: Logs MIME type (toy)
- `log_storage_location_activity`: Logs storage location (toy)
- Expandable: Will be replaced with real PDF parsing, LLM calls, etc.

```python
@activity.defn
async def log_mime_type_activity(mime_type: str) -> str: ...

@activity.defn
async def log_storage_location_activity(storage_location: str) -> str: ...
```

#### 2.2 Temporal Orchestrator Implementation

**`infrastructure/temporal/orchestrator.py`** (NEW)
- `TemporalWorkflowOrchestrator`: Implements `WorkflowOrchestrator` port
- Lazy-initializes Temporal client
- Uses artifact_id as workflow ID for idempotency
- Handles connection, workflow startup, error handling

```python
class TemporalWorkflowOrchestrator(WorkflowOrchestrator):
    async def start_artifact_processing_workflow(
        self,
        artifact_id: UUID,
        storage_location: str,
    ) -> None: ...
```

#### 2.3 Worker Processes

**`infrastructure/temporal/worker.py`** (NEW)
- Runs the Temporal worker process
- Polls for tasks from "artifact_processing" task queue
- Executes workflows and activities
- Registers all activities and workflows

```bash
# Start with:
python -m infrastructure.temporal.worker
```

**`infrastructure/pipeline_worker.py`** (NEW)
- Listens to EventStoreDB via `ApplicationSubscription`
- Similar pattern to `read_worker.py`
- Detects `ArtifactCreated` events
- Triggers Temporal workflows via orchestrator
- Independent from read model projector

```bash
# Start with:
python -m infrastructure.pipeline_worker
```

#### 2.4 Configuration

**`infrastructure/config.py`** (MODIFIED)
- Added `temporal_address` setting
- Defaults to `localhost:7233`
- Configurable via `TEMPORAL_ADDRESS` env var

```python
temporal_address: str = Field(
    default="localhost:7233",
    validation_alias="TEMPORAL_ADDRESS",
)
```

#### 2.5 Dependency Injection

**`infrastructure/di/container.py`** (MODIFIED)
- Added import for `WorkflowOrchestrator` port
- Added import for `TemporalWorkflowOrchestrator` implementation
- Registered orchestrator in DI container

```python
container[WorkflowOrchestrator] = lambda _: TemporalWorkflowOrchestrator()
```

### 3. Build Configuration

**`pyproject.toml`** (MODIFIED)
- Added `temporalio>=1.3.0` dependency
- Now required for Temporal SDK

**`Makefile`** (MODIFIED)
- Added `run-workflow-worker` target
- Added `run-temporal-worker` target
- Both integrated into development workflow

```makefile
run-workflow-worker: ## Run the Temporal workflow orchestration worker
	uv run python -m infrastructure.pipeline_worker

run-temporal-worker: ## Run the Temporal workflow worker
	uv run python -m infrastructure.temporal.worker
```

### 4. Documentation

**`PIPELINE_ARCHITECTURE.md`** (NEW)
- Comprehensive architecture documentation
- Explains design principles and patterns
- Shows how to extend with new activities
- Testing strategy
- Deployment considerations

**`PIPELINE_QUICKSTART.md`** (NEW)
- Step-by-step quick start guide
- How to run locally
- What happens internally
- Troubleshooting guide
- Next steps for expansion

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│ Application Layer                                       │
├─────────────────────────────────────────────────────────┤
│ • CreateArtifactUseCase                                 │
│ • WorkflowOrchestrator (port - abstraction)             │
│ • UpdateSummaryCandidateUseCase (future)                │
└──────────────────────┬──────────────────────────────────┘
                       │ depends on
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Infrastructure Layer - Event Subscription               │
├─────────────────────────────────────────────────────────┤
│ • pipeline_worker.py (listens to EventStoreDB)          │
│ • Detects ArtifactCreated events                        │
│ • Triggers orchestrator.start_artifact_processing()     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Infrastructure Layer - Temporal Orchestration           │
├─────────────────────────────────────────────────────────┤
│ • TemporalWorkflowOrchestrator (implements port)        │
│ • Starts workflow with artifact_id as workflow ID       │
│ • Ensures idempotency                                   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Infrastructure Layer - Temporal Workflow Execution      │
├─────────────────────────────────────────────────────────┤
│ • temporal/worker.py (polls for tasks)                  │
│ • ProcessArtifactWorkflow workflow                      │
│ • Orchestrates activities                               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Infrastructure Layer - Activities (Expandable)          │
├─────────────────────────────────────────────────────────┤
│ • log_mime_type_activity (toy)                          │
│ • log_storage_location_activity (toy)                   │
│ • parse_pdf_activity (future)                           │
│ • llm_summarize_activity (future)                       │
└─────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Event-Driven (No Kafka for Pipeline Trigger)
- Uses EventStoreDB subscription like read_worker.py
- Same event stream powers multiple independent workers
- Simpler than Kafka for internal orchestration
- Kafka still available for external subscribers

### 2. Idempotency via Workflow ID
- `workflow_id = str(artifact_id)`
- Same artifact never processed twice
- Safe to replay events

### 3. Separation of Concerns
- **Domain**: What to do (Artifact aggregate, events)
- **Application**: When to do it (CreateArtifactUseCase, WorkflowOrchestrator port)
- **Infrastructure**: How to do it (Temporal, activities, workers)

### 4. Port-Based Architecture
- Application depends on `WorkflowOrchestrator` port
- Infrastructure implements port with Temporal
- Can swap implementations without changing business logic
- Enables testing with mock orchestrators

### 5. Independent Workers
- `pipeline_worker.py`: Triggers workflows (independent process)
- `temporal/worker.py`: Executes workflows (independent process)
- `read_worker.py`: Updates read models (existing)
- All subscribe to same EventStoreDB stream
- Can scale each independently

## Running the System

```bash
# Terminal 1: Temporal Worker (executes workflows/activities)
make run-temporal-worker

# Terminal 2: Pipeline Worker (triggers workflows on events)
make run-workflow-worker

# Terminal 3: API Server (handles requests)
make run

# Then: Create an artifact to trigger the workflow
curl -X POST http://localhost:8000/artifacts -F "file=@file.pdf" ...
```

## Expandability Path

1. **Current**: Toy activities that log details
2. **Next**: Real PDF parsing activity
3. **Next**: Page extraction activity
4. **Next**: LLM summarization activity
5. **Next**: Update artifact with results (emit domain events)
6. **Production**: Full workflow with monitoring, dead letters, etc.

All without changing the architecture or the domain!

## Testing Strategy

- **Unit**: Test domain and activities in isolation
- **Integration**: Test workflows with test client
- **End-to-end**: Run full stack locally

See [PIPELINE_ARCHITECTURE.md](PIPELINE_ARCHITECTURE.md) for details.

## Deployment

```bash
# Development (localhost)
make docker-up
make run-temporal-worker
make run-workflow-worker
make run

# Production (considerations)
# - Multiple Temporal server instances (cluster)
# - Multiple workers (scale independently)
# - Load balancing for API servers
# - Monitoring/alerting on workflow failures
# - Retention policies for old workflows
```