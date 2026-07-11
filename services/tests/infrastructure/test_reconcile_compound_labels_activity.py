import asyncio
from uuid import uuid4

from returns.result import Success

from application.dtos.reconcile_dtos import LabelChange, ReconcileResultDTO
from infrastructure.temporal.activities.reconcile_compound_labels_activities import (
    create_reconcile_compound_labels_activity,
)


class FakeUseCase:
    def __init__(self, dto):
        self._dto = dto
        self.called_with = None

    async def execute(self, page_id):
        self.called_with = page_id
        return Success(self._dto)


def test_activity_maps_success_dto_to_dict():
    page_id = uuid4()
    dto = ReconcileResultDTO(
        page_id=page_id,
        artifact_id=uuid4(),
        changes=[LabelChange(before="CMX41O", after="CMX410")],
        applied=True,
    )
    activity_fn = create_reconcile_compound_labels_activity(use_case=FakeUseCase(dto))

    out = asyncio.run(activity_fn(str(page_id)))

    assert out == {"status": "success", "page_id": str(page_id), "changed": 1, "applied": True}
