# Adding a New ML/External Service

Step-by-step checklist for integrating a new external service (ML model, API, etc.) that processes pages or artifacts and writes results back to the domain. Follow the compound extraction feature as the reference implementation.

---

## 1. DTO — raw service output

**`application/dtos/<service>_dtos.py`**
```python
class MyServiceResult(BaseModel):
    field_a: str | None
    field_b: float | None
```
This is the raw shape returned by your service, before any domain mapping.

---

## 2. Port — abstract interface

**`application/ports/<service>_service.py`**
```python
class MyService(Protocol):
    def process_pdf_page(self, storage_key: str, page_index: int) -> list[MyServiceResult]: ...
```
- Use `Protocol` (not ABC)
- Accept `storage_key` + `page_index` if you need the page image; adjust signature if different
- Return DTOs, not domain objects

---

## 3. Use case — domain logic

**`application/use_cases/<service>_use_cases.py`**
```python
class MyExtractionUseCase:
    def __init__(self, page_repository, artifact_repository, my_service, external_event_publisher=None): ...

    async def execute(self, page_id: UUID) -> Result[PageResponse, AppError]:
        page = self.page_repository.get_by_id(page_id)
        artifact = self.artifact_repository.get_by_id(page.artifact_id)
        raw = self.my_service.process_pdf_page(artifact.storage_location, page.index)
        domain_objects = [map(r) for r in raw if is_valid(r)]
        page.update_my_field(domain_objects)          # call the aggregate command
        self.page_repository.save(page)
        ...
        return Success(PageMapper.to_page_response(page))
```
Catch `AggregateNotFoundError`, `ValidationError`, `ConcurrencyError` → return `Failure(AppError(...))`.

---

## 4. Workflow use case — trigger

**`application/workflow_use_cases/trigger_<service>_use_case.py`**
```python
class TriggerMyExtractionUseCase:
    def __init__(self, page_repository, workflow_orchestrator): ...

    async def execute(self, page_id: UUID) -> WorkflowStatus:
        page = self.page_repository.get_by_id(page_id)
        status = WorkflowStatus.in_progress(workflow_id=uuid4(), message="...")
        page.update_workflow_status(WorkflowNames.MY_WORKFLOW, status)
        self.page_repository.save(page)
        await self.workflow_orchestrator.start_my_workflow(page_id=page_id)
        return status
```

---

## 5. Infrastructure — service implementation

**`infrastructure/<service>/<service>_impl.py`**
```python
class MyServiceImpl(MyService):
    def __init__(self, blob_store: BlobStore): ...

    def _ensure_loaded(self):
        if self._model is None:
            from some_lib import Model
            self._model = Model()          # lazy load

    def process_pdf_page(self, storage_key, page_index):
        import fitz
        self._ensure_loaded()
        with self._blob_store.get_file(storage_key) as path:
            pix = fitz.open(path)[page_index].get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        pairs = self._model.process(img)
        return [MyServiceResult(...) for p in pairs]
```

---

## 6. Temporal workflow

**`infrastructure/temporal/workflows/<service>_workflow.py`**
```python
@workflow.defn(name="MyWorkflow")
class MyWorkflow:
    @workflow.run
    async def run(self, page_id: str) -> dict:
        return await workflow.execute_activity(
            "my_activity_name",
            page_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0),
        )
```
Set timeout generously for slow ML models.

---

## 7. Temporal activity

**`infrastructure/temporal/activities/<service>_activities.py`**
```python
def create_my_activity(use_case: MyExtractionUseCase):
    @activity.defn(name="my_activity_name")
    async def my_activity(page_id: str) -> dict:
        result = await use_case.execute(UUID(page_id))
        if isinstance(result, Success):
            return {"status": "success", "page_id": page_id, ...}
        error = result.failure()
        return {"status": "failed", "error_code": error.category, ...}
    return my_activity
```
Re-raise exceptions so Temporal retries: `except Exception: raise`.

---

## 8. Wire everything

**`application/ports/workflow_orchestrator.py`** — add abstract method:
```python
@abstractmethod
async def start_my_workflow(self, page_id: UUID) -> None: ...
```

**`infrastructure/temporal/orchestrator.py`** — implement it:
```python
async def start_my_workflow(self, page_id: UUID) -> None:
    await self._ensure_client()
    await self._client.start_workflow(
        "MyWorkflow", str(page_id),
        id=f"my-workflow-{page_id}",
        task_queue="artifact_processing",
    )
```

**`infrastructure/temporal/worker.py`** — register:
```python
my_use_case = container[MyExtractionUseCase]
my_activity = create_my_activity(use_case=my_use_case)

worker = Worker(...,
    workflows=[..., MyWorkflow],
    activities=[..., my_activity],
)
```

**`infrastructure/di/container.py`** — register all three:
```python
container[MyService] = lambda c: MyServiceImpl(blob_store=c[BlobStore])
container[MyExtractionUseCase] = lambda c: MyExtractionUseCase(
    page_repository=c[PageRepository],
    artifact_repository=c[ArtifactRepository],
    my_service=c[MyService],
    external_event_publisher=c[ExternalEventPublisher],
)
container[TriggerMyExtractionUseCase] = lambda c: TriggerMyExtractionUseCase(
    page_repository=c[PageRepository],
    workflow_orchestrator=c[WorkflowOrchestrator],
)
```

**`application/dtos/workflow_dtos.py`** — add constant:
```python
class WorkflowNames(str, Enum):
    MY_WORKFLOW = "my_workflow"
```

---

## 9. Automatic trigger

**`infrastructure/pipeline_worker.py`** — add topic + handler:
```python
topics = [
    ...,
    f"{Page.Created.__module__}:{Page.Created.__qualname__}",  # or another event
]

# in the event loop:
if isinstance(domain_event, Page.Created):
    await trigger_my_extraction_use_case.execute(page_id=domain_event.originator_id)
```
Resolve `TriggerMyExtractionUseCase` from container at startup.

---

## 10. Manual trigger (API)

**`interfaces/api/routes/page_routes.py`** — add endpoint:
```python
@router.post("/{page_id}/my-thing/extract", status_code=status.HTTP_202_ACCEPTED)
async def trigger_my_extraction(page_id: UUID, container: ...) -> WorkflowStatus:
    use_case = container[TriggerMyExtractionUseCase]
    try:
        return await use_case.execute(page_id=page_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
```

---

## Checklist

- [ ] `application/dtos/<service>_dtos.py` — raw output DTO
- [ ] `application/ports/<service>_service.py` — Protocol port
- [ ] `application/use_cases/<service>_use_cases.py` — extraction use case
- [ ] `application/workflow_use_cases/trigger_<service>_use_case.py` — workflow trigger
- [ ] `application/dtos/workflow_dtos.py` — add `WorkflowNames` entry
- [ ] `application/ports/workflow_orchestrator.py` — add abstract method
- [ ] `infrastructure/<service>/` — service implementation (lazy-load model)
- [ ] `infrastructure/temporal/workflows/<service>_workflow.py` — Temporal workflow
- [ ] `infrastructure/temporal/activities/<service>_activities.py` — activity factory
- [ ] `infrastructure/temporal/orchestrator.py` — implement orchestrator method
- [ ] `infrastructure/temporal/worker.py` — register workflow + activity
- [ ] `infrastructure/di/container.py` — wire port, use cases
- [ ] `infrastructure/pipeline_worker.py` — add event topic + handler
- [ ] `interfaces/api/routes/page_routes.py` — add 202 endpoint
