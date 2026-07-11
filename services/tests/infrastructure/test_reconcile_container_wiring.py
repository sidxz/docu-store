from application.use_cases.reconcile_compound_labels_use_case import (
    ReconcileCompoundLabelsUseCase,
)
from application.workflow_use_cases.trigger_compound_label_reconciliation_use_case import (
    TriggerCompoundLabelReconciliationUseCase,
)
from infrastructure.di.container import create_container


def test_container_resolves_reconcile_use_cases():
    container = create_container()
    assert isinstance(container[ReconcileCompoundLabelsUseCase], ReconcileCompoundLabelsUseCase)
    assert isinstance(
        container[TriggerCompoundLabelReconciliationUseCase],
        TriggerCompoundLabelReconciliationUseCase,
    )
