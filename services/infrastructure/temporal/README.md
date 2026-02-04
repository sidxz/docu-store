# Temporal Integration for PDF Processing

This directory contains the Temporal workflow integration for automatic PDF processing in the docu-store service.

## Architecture Overview

Following DDD and Event Sourcing principles:

- **Application Layer** (`application/use_cases/`): Contains business logic
  - `ExtractPdfContentUseCase`: Extracts first N words from PDF first page
  - `CreateArtifactWithTitleUseCase`: Creates artifact with extracted text as title

- **Infrastructure Layer** (`infrastructure/temporal/`): Temporal orchestration
  - `activities/`: Temporal activities that call application use cases
  - `workflows/`: Workflow definitions for orchestrating activities
  - `temporal_worker.py`: Worker service that executes workflows

## Toy Example Workflow: PDF Ingestion

When a blob is uploaded, the `PdfIngestionWorkflow` orchestrates:

1. **Check if PDF**: Validates file is a PDF
2. **Extract Content**: Extracts first 20 words from first page
3. **Create Artifact**: Creates artifact with extracted text as title

## Setup

### Prerequisites

1. Install dependencies:
   ```bash
   pip install -e .
   ```

2. Start Temporal server (using Docker):
   ```bash
   docker run -p 7233:7233 -p 8233:8233 temporalio/auto-setup:latest
   ```

3. Start EventStoreDB (KurrentDB):
   ```bash
   # Your existing EventStoreDB setup
   ```

### Running the Temporal Worker

The Temporal worker processes workflows by executing activities:

```bash
python -m infrastructure.temporal.temporal_worker
```

This will:
- Connect to Temporal server at `localhost:7233`
- Register workflows and activities
- Listen on task queue `docu-store-task-queue`
- Execute workflows when triggered

## Usage

### Triggering a Workflow Programmatically

```python
from uuid import uuid4
from temporalio.client import Client
from infrastructure.temporal.workflows.pdf_ingestion_workflow import (
    PdfIngestionWorkflow,
    PdfIngestionInput,
)

# Connect to Temporal
client = await Client.connect("localhost:7233")

# Trigger workflow
workflow_id = f"pdf-ingestion-{uuid4()}"
result = await client.execute_workflow(
    PdfIngestionWorkflow.run,
    PdfIngestionInput(
        artifact_id=str(uuid4()),
        storage_key="artifacts/abc123/source.pdf",
        filename="document.pdf",
        mime_type="application/pdf",
        source_uri="https://example.com/document.pdf",
    ),
    id=workflow_id,
    task_queue="docu-store-task-queue",
)

print(f"Workflow completed: {result}")
```

### Using TemporalWorkerService Helper

```python
from infrastructure.temporal.temporal_worker import TemporalWorkerService

# Create service
service = TemporalWorkerService()
await service.start()  # Run in background

# Trigger workflow
workflow_id = await service.trigger_pdf_ingestion_workflow(
    storage_key="artifacts/xyz/source.pdf",
    filename="paper.pdf",
    mime_type="application/pdf",
    source_uri="https://arxiv.org/paper.pdf",
)
```

## Integration with Event Sourcing

### Current Implementation (Toy Example)

The toy example uses direct workflow triggering rather than event-based triggers, since:
- Blobs are temporary and don't have domain aggregates
- We want to keep the example simple and focused

### Future Enhancement: Event-Driven Workflows

For production, you could:

1. **Create a BlobUploaded domain event** in an aggregate
2. **Subscribe to events** using `ApplicationSubscription`:
   ```python
   subscription = ApplicationSubscription(
       app,
       topics=["application.events:BlobUploaded"],
   )
   
   for event, tracking in subscription:
       await temporal_service.trigger_pdf_ingestion_workflow(
           storage_key=event.storage_key,
           filename=event.filename,
           ...
       )
   ```

3. **Track processed events** to ensure idempotency

## Workflow Configuration

### Retry Policies

Activities are configured with retry policies:

```python
retry_policy=workflow.RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)
```

### Timeouts

- **check_if_pdf**: 10 seconds
- **extract_pdf_first_page_content**: 30 seconds (with retries)
- **create_artifact_with_title**: 30 seconds (with retries)

## Monitoring

### Temporal UI

Access the Temporal UI at `http://localhost:8233` to:
- View workflow execution history
- Inspect activity results
- Debug failures
- Replay workflows

### Logging

The worker uses `structlog` for structured logging:

```python
logger.info("workflow_triggered", workflow_id=workflow_id, storage_key=storage_key)
```

## Testing

### Manual Testing

1. Start the worker:
   ```bash
   python -m infrastructure.temporal.temporal_worker
   ```

2. Upload a PDF blob (use your existing API)

3. Trigger the workflow programmatically

4. Check Temporal UI for workflow execution

5. Verify artifact created in EventStoreDB

### Unit Testing Activities

```python
from infrastructure.temporal.activities.pdf_processing_activities import (
    PdfProcessingActivities,
)

# Test with mocked use cases
activities = PdfProcessingActivities(
    extract_pdf_content_use_case=mock_extract_use_case,
    create_artifact_with_title_use_case=mock_create_use_case,
)

result = await activities.check_if_pdf("document.pdf", "application/pdf")
assert result is True
```

## Architecture Benefits

### Separation of Concerns

- **Application Layer**: Pure business logic, no Temporal dependencies
- **Infrastructure Layer**: Orchestration, no business logic

### Testability

- Use cases can be tested independently
- Activities can be tested with mocked use cases
- Workflows can be tested using Temporal test framework

### Event Sourcing Compatibility

- Workflows complement event sourcing
- Long-running processes handled by Temporal
- Aggregate state changes handled by event sourcing
- Best of both worlds

## Common Issues

### Worker Not Starting

- Check Temporal server is running: `docker ps`
- Verify connection: `telnet localhost 7233`
- Check logs for connection errors

### Workflow Not Executing

- Verify worker is running
- Check task queue name matches
- Ensure workflow is registered

### Activity Failures

- Check use case dependencies are properly injected
- Verify blob storage is accessible
- Check EventStoreDB is running
- Review activity logs for specific errors

## Next Steps

1. **Add more workflows**: Document classification, text extraction, etc.
2. **Event-based triggering**: Subscribe to domain events
3. **Saga patterns**: Implement compensation logic for failures
4. **Advanced features**: Signals, queries, child workflows
5. **Production hardening**: Error handling, monitoring, alerting
