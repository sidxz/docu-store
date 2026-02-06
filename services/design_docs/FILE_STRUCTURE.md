# New File Structure

## Visual Tree of All New Files

```
services/
├── application/
│   └── ports/
│       └── pipeline_orchestrator.py ........................ NEW (Port/Interface)
│
├── infrastructure/
│   ├── temporal/ .......................................... NEW (Package)
│   │   ├── __init__.py .................................... NEW
│   │   ├── orchestrator.py ................................. NEW (Implements Port)
│   │   ├── worker.py ....................................... NEW (Temporal Worker Process)
│   │   ├── workflows/
│   │   │   ├── __init__.py ................................. NEW
│   │   │   └── artifact_processing.py ....................... NEW (Workflow Definition)
│   │   └── activities/
│   │       ├── __init__.py ................................. NEW
│   │       └── artifact_activities.py ....................... NEW (Activity Implementations)
│   │
│   ├── config.py ........................................... MODIFIED (Added temporal_address)
│   ├── di/
│   │   └── container.py .................................... MODIFIED (Registered Orchestrator)
│   │
│   └── pipeline_worker.py .................................. NEW (Event-Driven Worker Process)
│
├── pyproject.toml .......................................... MODIFIED (Added temporalio dependency)
├── Makefile ................................................ MODIFIED (Added make targets)
│
└── Documentation Files:
    ├── PIPELINE_ARCHITECTURE.md ............................. NEW (Comprehensive Design)
    ├── PIPELINE_QUICKSTART.md ............................... NEW (Local Setup Guide)
    ├── ARCHITECTURE_DIAGRAMS.md ............................. NEW (Visual Diagrams)
    ├── TESTING_PIPELINE.md .................................. NEW (Testing Guide)
    ├── IMPLEMENTATION_SUMMARY.md ............................. NEW (Change Summary)
    └── CHANGELOG.md ......................................... NEW (This Overview)
```

## File Dependency Graph

```
┌─────────────────────────────────────────────────┐
│ Application Layer (Domain-Independent)          │
├─────────────────────────────────────────────────┤
│                                                 │
│  PipelineOrchestrator (port)                   │
│  └─ Abstraction: What orchestration must do    │
│                                                 │
└───────────────────┬─────────────────────────────┘
                    │ depends on (abstraction)
                    ↓
┌─────────────────────────────────────────────────┐
│ Infrastructure Layer - Temporal Implementation  │
├─────────────────────────────────────────────────┤
│                                                 │
│  TemporalPipelineOrchestrator                   │
│  └─ Implementation: How Temporal does it        │
│                                                 │
└───────────────────┬─────────────────────────────┘
                    │ uses
                    ↓
┌─────────────────────────────────────────────────┐
│ Infrastructure Layer - Workers & Processes      │
├─────────────────────────────────────────────────┤
│                                                 │
│  pipeline_worker.py                             │
│  ├─ Listens to: EventStoreDB                   │
│  ├─ Detects: ArtifactCreated events            │
│  └─ Calls: orchestrator.start_*()              │
│                                                 │
│  temporal/worker.py                             │
│  ├─ Listens to: Temporal Server                │
│  ├─ Executes: ProcessArtifactPipeline workflow │
│  └─ Runs: All registered activities            │
│                                                 │
└───────────────────┬─────────────────────────────┘
                    │ uses
                    ↓
┌─────────────────────────────────────────────────┐
│ Infrastructure Layer - Temporal Workflow        │
├─────────────────────────────────────────────────┤
│                                                 │
│  ProcessArtifactPipeline (workflow)             │
│  └─ Orchestrates activity execution            │
│                                                 │
└───────────────────┬─────────────────────────────┘
                    │ calls
                    ↓
┌─────────────────────────────────────────────────┐
│ Infrastructure Layer - Activities               │
├─────────────────────────────────────────────────┤
│                                                 │
│  log_mime_type_activity                         │
│  log_storage_location_activity                  │
│  [Future: parse_pdf_activity]                   │
│  [Future: llm_summarize_activity]               │
│  [Future: update_artifact_activity]             │
│                                                 │
└─────────────────────────────────────────────────┘
```

## Interaction Sequence

```
1. User creates artifact
   API (main.py)
   ↓
   CreateArtifactUseCase
   ↓
   EventStoreDB (saves ArtifactCreated event)
   
2. Pipeline triggered
   EventStoreDB (emits event)
   ↓
   pipeline_worker.py (subscribes, detects event)
   ↓
   TemporalPipelineOrchestrator (starts workflow)
   
3. Workflow execution
   Temporal Server
   ↓
   temporal/worker.py (polls for tasks)
   ↓
   ProcessArtifactPipeline (runs workflow)
   ↓
   artifact_activities.py (execute activities)
```

## Key Concepts

### Port (Abstraction)
```
application/ports/pipeline_orchestrator.py
├─ Abstract class: PipelineOrchestrator
├─ Method: start_artifact_processing_pipeline()
└─ Implementation-agnostic
```

### Implementation
```
infrastructure/temporal/orchestrator.py
├─ Concrete class: TemporalPipelineOrchestrator
├─ Implements: PipelineOrchestrator
└─ Uses: Temporal SDK
```

### Workers (Independent Processes)
```
infrastructure/pipeline_worker.py
├─ Subscribes to: EventStoreDB
├─ Triggers: Workflows
└─ Process: Can run separately

infrastructure/temporal/worker.py
├─ Connects to: Temporal Server
├─ Executes: Workflows & activities
└─ Process: Can run separately
```

### Workflow
```
infrastructure/temporal/workflows/artifact_processing.py
├─ @workflow.defn ProcessArtifactPipeline
├─ Orchestrates: Activities
└─ Handles: Retries, timeouts, errors
```

### Activities
```
infrastructure/temporal/activities/artifact_activities.py
├─ @activity.defn log_mime_type_activity
├─ @activity.defn log_storage_location_activity
└─ Extensible for more activities
```

## How to Use These Files

### To Understand the Architecture
1. Read: `PIPELINE_ARCHITECTURE.md`
2. Read: `ARCHITECTURE_DIAGRAMS.md`
3. Look at: `application/ports/pipeline_orchestrator.py`

### To Run Locally
1. Follow: `PIPELINE_QUICKSTART.md`
2. Start terminals:
   - `make run-temporal-worker`
   - `make run-pipeline-worker`
   - `make run`
3. Test: `TESTING_PIPELINE.md`

### To Extend the Pipeline
1. Add activity to: `infrastructure/temporal/activities/artifact_activities.py`
2. Update workflow in: `infrastructure/temporal/workflows/artifact_processing.py`
3. Register in worker: `infrastructure/temporal/worker.py`

### To Test
1. Unit tests: Mock `PipelineOrchestrator` port
2. Integration tests: Use Temporal test client
3. E2E tests: Follow `TESTING_PIPELINE.md`

## Configuration Points

### Runtime Configuration
```
infrastructure/config.py
├─ temporal_address (default: localhost:7233)
├─ Environment: TEMPORAL_ADDRESS
└─ Used by: TemporalPipelineOrchestrator
```

### DI Container Registration
```
infrastructure/di/container.py
├─ container[PipelineOrchestrator] = TemporalPipelineOrchestrator()
├─ Loaded by: pipeline_worker.py, (future) use cases
└─ Allows: Easy mocking for tests
```

### Task Queue
```
Both workers use: "artifact_processing" task queue
├─ Configurable: In worker.py, workflow start_workflow()
├─ Independent: Can have multiple queues for different workloads
└─ Scalable: Add more workers to same queue
```

## Scale Path

### Single Machine Development
```
1 Temporal Server (docker)
1 pipeline worker
1 temporal worker
1 API server
```

### Production
```
3+ Temporal Servers (cluster)
N pipeline workers (independent horizontal scaling)
M temporal workers (independent horizontal scaling)
L API servers (behind load balancer)
```

## Monitoring & Observability

### Temporal UI
- URL: http://localhost:8233
- Shows: All workflow executions, activity timings, errors
- Access: After `docker-compose up` and running workers

### Logs
- Terminal 1 (temporal/worker.py): Activity execution logs
- Terminal 2 (pipeline_worker.py): Event detection logs
- Terminal 3 (API server): Request logs
- Docker: Service logs via `docker logs`

### Metrics
- Temporal UI shows: Workflow count, success/failure rates
- structlog integration: All events structured for metrics
- Extensible: Add Prometheus/Datadog exporters
