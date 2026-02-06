# Architecture Diagrams

## 1. Component Interaction Diagram

```
                            ┌────────────────────────────────────────┐
                            │      API Server (main.py)              │
                            │   - Handles HTTP requests               │
                            │   - Calls use cases                     │
                            └────────────┬─────────────────────────────┘
                                         │
                                         │ POST /artifacts
                                         │ (upload file)
                                         ↓
                            ┌────────────────────────────────────────┐
                            │   CreateArtifactUseCase                │
                            │   (application/use_cases/)              │
                            │   - Create Artifact aggregate           │
                            │   - Save to repository                  │
                            └────────────┬─────────────────────────────┘
                                         │
                                         │ artifact_repository.save()
                                         ↓
                            ┌────────────────────────────────────────┐
                            │     EventStoreDB (Event Store)         │
                            │   - Artifact aggregate saved             │
                            │   - ArtifactCreated event emitted       │
                            └────────────┬─────────────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                    │
                    ↓                    ↓                    ↓
        ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
        │  read_worker.py  │  │pipeline_worker.py│  │  Other systems   │
        │  (Projector)     │  │ (Pipeline Trigger)│  │  (via Kafka)     │
        │                  │  │                   │  │                  │
        │ Updates MongoDB  │  │ Starts Temporal  │  │ External events  │
        │ read models      │  │ workflows        │  │                  │
        └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘
                 │                     │
                 │                     ↓
                 │        ┌────────────────────────────────────────┐
                 │        │ TemporalPipelineOrchestrator           │
                 │        │ (infrastructure/temporal/orchestrator) │
                 │        │                                        │
                 │        │ - Lazy-init Temporal client           │
                 │        │ - Start workflow with artifact_id      │
                 │        │ - Ensure idempotency                   │
                 │        └────────────┬──────────────────────────┘
                 │                     │
                 │                     │ Temporal.start_workflow()
                 │                     ↓
                 │        ┌────────────────────────────────────────┐
                 │        │  Temporal Server Backend               │
                 │        │  - Stores workflow state               │
                 │        │  - Manages execution history           │
                 │        │ (Running in docker-compose)            │
                 │        └────────────┬──────────────────────────┘
                 │                     │
                 │                     │ Task assigned to worker
                 │                     ↓
                 │        ┌────────────────────────────────────────┐
                 │        │  temporal/worker.py                    │
                 │        │  - Polls for tasks                     │
                 │        │  - Executes workflows                  │
                 │        └────────────┬──────────────────────────┘
                 │                     │
                 │                     ↓
                 │        ┌────────────────────────────────────────┐
                 │        │ ProcessArtifactPipeline (workflow)     │
                 │        │                                        │
                 │        │ Execute steps:                         │
                 │        │ 1. log_mime_type_activity             │
                 │        │ 2. log_storage_location_activity      │
                 │        │ 3. [Future: parse_pdf_activity]       │
                 │        │ 4. [Future: llm_summarize_activity]   │
                 │        └────────────┬──────────────────────────┘
                 │                     │
                 │                     │ Each activity
                 │                     ↓
                 │        ┌────────────────────────────────────────┐
                 │        │ Activities (artifact_activities.py)    │
                 │        │                                        │
                 │        │ - log_mime_type_activity              │
                 │        │ - log_storage_location_activity       │
                 │        │ [Future: Real PDF parsing, LLM, etc]  │
                 │        └────────────┬──────────────────────────┘
                 │                     │
                 │        [Future: Results written back to]
                 │        [domain via UpdateSummaryCandidateUseCase]
                 │                     │
                 │                     ↓
                 │        ┌────────────────────────────────────────┐
                 │        │ [Future: New events emitted]           │
                 │        │ [Propagate back to read models]        │
                 │        └────────────────────────────────────────┘
                 │
                 ↓
        ┌──────────────────────────┐
        │  MongoDB Read Models     │
        │  - artifact_read_models  │
        │  - page_read_models      │
        │  (Queryable for UI/API)  │
        └──────────────────────────┘
```

## 2. Data Flow: From Upload to Pipeline Execution

```
Time ───→

Step 1: Upload
┌─────────────────────────────────────────────────────────┐
│ curl POST /artifacts -F "file=@document.pdf"            │
│ └─ API Server receives request                          │
│    └─ CreateArtifactUseCase.execute(request)            │
│       └─ Artifact.create() [domain model]               │
│          └─ Save to ArtifactRepository                  │
│             └─ EventStoreDB: persist ArtifactCreated    │
└──────────────────────┬──────────────────────────────────┘
                       │
Step 2: Event Propagation (simultaneous to multiple workers)
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ↓              ↓              ↓
    ┌─────────┐  ┌──────────┐  ┌────────────┐
    │read     │  │pipeline  │  │[Kafka: opt]│
    │worker   │  │worker    │  │            │
    │updates  │  │starts    │  │publishes   │
    │MongoDB  │  │Temporal  │  │events      │
    └────┬────┘  └──┬───────┘  └────────────┘
         │          │
Step 3: Workflow Execution (in pipeline_worker)
         │          │
         │          ├─ orchestrator.start_artifact_processing_pipeline(
         │          │     artifact_id=uuid,
         │          │     storage_location="/path/to/file"
         │          │ )
         │          │
         │          ├─ Temporal.start_workflow(
         │          │     ProcessArtifactPipeline.execute,
         │          │     id=str(artifact_id),  # idempotent!
         │          │     task_queue="artifact_processing"
         │          │ )
         │          │
         │          └─ Workflow starts in Temporal backend
         │
Step 4: Worker Polling and Execution
         │
         └─ temporal/worker.py polls Temporal
            ├─ Receives ProcessArtifactPipeline task
            │
            ├─ Execute workflow:
            │  ├─ await log_mime_type_activity("application/pdf")
            │  │  └─ Logs: "Logged MIME type: application/pdf"
            │  │
            │  └─ await log_storage_location_activity("/path/to/file")
            │     └─ Logs: "Logged storage location: /path/to/file"
            │
            └─ Workflow completes successfully
```

## 3. System Architecture - Process View

```
Local Development Setup:

┌─────────────────────────────────────────────────────────────────┐
│  Terminal 1: Temporal Worker                                    │
│  $ make run-temporal-worker                                     │
│                                                                 │
│  Process: infrastructure/temporal/worker.py                    │
│  - Connects to: Temporal Server @ localhost:7233              │
│  - Task Queue: "artifact_processing"                          │
│  - Registers: Workflows + Activities                          │
│  - Polls: For new workflow tasks                              │
│  - Executes: ProcessArtifactPipeline                          │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   │ Temporal binary protocol (localhost:7233)
                   │
                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  Docker: Temporal Server                                        │
│  Image: temporalio/server:1.29.2                               │
│  Port: 7233 (gRPC for workflows)                               │
│  Database: PostgreSQL (event log)                              │
│  UI: http://localhost:8233 (view workflow history)            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Terminal 2: Pipeline Worker                                    │
│  $ make run-pipeline-worker                                     │
│                                                                 │
│  Process: infrastructure/pipeline_worker.py                    │
│  - Connects to: EventStoreDB @ localhost:2113                 │
│  - Subscribes: ArtifactCreated events                         │
│  - Uses: ApplicationSubscription pattern                      │
│  - Triggers: orchestrator.start_artifact_processing()         │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   │ gRPC (localhost:2113)
                   │
                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  Docker: EventStoreDB                                           │
│  Image: eventstore/eventstore:24.10.0                          │
│  Port: 2113 (gRPC + HTTP)                                      │
│  Database: Event log (append-only)                             │
│  UI: http://localhost:2113 (projections + events)             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Terminal 3: API Server                                         │
│  $ make run                                                     │
│                                                                 │
│  Process: interfaces/api/main.py (FastAPI)                     │
│  - Listens: http://localhost:8000                              │
│  - Endpoints: POST /artifacts (upload + create)               │
│  - Uses: CreateArtifactUseCase                                │
│  - Persists to: EventStoreDB                                  │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   │ gRPC (localhost:2113)
                   │
                   ↓
        (same EventStoreDB as above)

┌─────────────────────────────────────────────────────────────────┐
│  Docker: Supporting Services                                    │
│  - MongoDB: http://localhost:27017 (read models)              │
│  - Kafka: localhost:19092 (optional, for external events)     │
│  - Kafka UI: http://localhost:5051                            │
│  - PostgreSQL: localhost:5432 (Temporal backend)              │
└─────────────────────────────────────────────────────────────────┘
```

## 4. Class Hierarchy

```
                    ┌─────────────────────┐
                    │ PipelineOrchestrator│ (port/interface)
                    │     (ABC)           │
                    └──────────┬──────────┘
                               │ implements
                               ↓
                    ┌─────────────────────────────────┐
                    │TemporalPipelineOrchestrator     │
                    │                                 │
                    │ - _client: Temporal Client      │
                    │ - start_artifact_processing_()  │
                    │   - async init client           │
                    │   - start workflow              │
                    │   - handle errors               │
                    └─────────────────────────────────┘

                    ┌─────────────────────┐
                    │ ProcessArtifactInput│ (DTO)
                    │                     │
                    │ - artifact_id       │
                    │ - storage_location  │
                    │ - mime_type         │
                    └─────────────────────┘

                    ┌──────────────────────────────┐
                    │ ProcessArtifactPipeline      │ (Workflow)
                    │                              │
                    │ @workflow.defn               │
                    │ def execute(...):            │
                    │   - log_mime_type_activity  │
                    │   - log_storage_location    │
                    │   [- future activities -]   │
                    └──────────────────────────────┘
```

## 5. Event Flow Sequence Diagram

```
User                API             CreateUseCase      EventStoreDB    Pipeline Worker   Temporal
│                   │                    │                  │                │             │
├──POST /artifacts──>│                    │                  │                │             │
│                   │                    │                  │                │             │
│                   ├─execute(request)──→│                  │                │             │
│                   │                    │                  │                │             │
│                   │                    ├─save artifact──→  │                │             │
│                   │                    │                  │                │             │
│                   │                    │ ← artifact saved │                │             │
│                   │                    │   (ArtifactCreated event)          │             │
│                   │                    │                  │                │             │
│                   │ ← artifact response←┤                  │                │             │
│                   │                    │                  │                │             │
│ ← 200 OK         │                    │                  │                │             │
│                   │                    │                  │                │             │
│                   │                    │                  ├─event from    │             │
│                   │                    │                  │ subscription   │             │
│                   │                    │                  │                ├─trigger    │
│                   │                    │                  │                │ workflow──>│
│                   │                    │                  │                │            │
│                   │                    │                  │                │            ├─poll
│                   │                    │                  │                │            │ for task
│                   │                    │                  │                │ ← assign  │
│                   │                    │                  │                │   task    │
│                   │                    │                  │                │            ├─execute
│                   │                    │                  │                │            │ activities
│                   │                    │                  │                │            │
│                   │                    │                  │                │            ├─log
│                   │                    │                  │                │            │ mime_type
│                   │                    │                  │                │            │
│                   │                    │                  │                │            ├─log
│                   │                    │                  │                │            │ storage
│                   │                    │                  │                │            │
│                   │                    │                  │                │ ← complete│
│                   │                    │                  │                │            │
│                   │                    │                  │                │            │
(View in Temporal UI: http://localhost:8233 to see workflow execution details)
```

## 6. Expanding the Pipeline

```
Current State (Toy):
─────────────────
┌──────────────────────────────────────────────────────────┐
│ ProcessArtifactPipeline                                  │
│                                                          │
│ ├─ Step 1: log_mime_type_activity (toy)               │
│ └─ Step 2: log_storage_location_activity (toy)        │
└──────────────────────────────────────────────────────────┘


Fully Expanded Pipeline (Future):
─────────────────────────────────
┌──────────────────────────────────────────────────────────┐
│ ProcessArtifactPipeline                                  │
│                                                          │
│ Phase 1: Extraction                                     │
│ ├─ parse_pdf_activity                                 │
│ │  └─ Use PyPDF2 / pdfplumber                         │
│ │                                                      │
│ └─ extract_first_page_activity                        │
│    └─ Get first page content/image                     │
│                                                        │
│ Phase 2: Enhancement                                   │
│ ├─ llm_summarize_activity                             │
│ │  └─ Call OpenAI/Claude API                          │
│ │                                                      │
│ └─ extract_metadata_activity                          │
│    └─ Get title, author, etc                          │
│                                                        │
│ Phase 3: Persistence                                   │
│ ├─ update_artifact_activity                           │
│ │  └─ UpdateSummaryCandidateUseCase                   │
│ │     └─ Emit events → read models updated            │
│ │                                                      │
│ └─ create_pages_activity                              │
│    └─ CreatePageUseCase for each page                 │
│       └─ Emit events → read models updated            │
│                                                        │
│ Phase 4: Notification                                 │
│ └─ notify_completion_activity                         │
│    └─ Send webhook / email / message                  │
│                                                        │
└──────────────────────────────────────────────────────────┘

All without changing the architecture!
Just add activities and register them in the worker.
```
