import asyncio
from uuid import uuid4

from application.workflow_use_cases.trigger_compound_label_reconciliation_use_case import (
    TriggerCompoundLabelReconciliationUseCase,
)


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def start_reconcile_compound_labels_workflow(self, page_id):
        self.calls.append(page_id)


def test_trigger_starts_workflow_and_returns_id():
    orch = FakeOrchestrator()
    uc = TriggerCompoundLabelReconciliationUseCase(workflow_orchestrator=orch)
    page_id = uuid4()

    resp = asyncio.run(uc.execute(page_id))

    assert orch.calls == [page_id]
    assert resp.workflow_id == f"reconcile-compound-labels-{page_id}"
