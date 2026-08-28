"""POST /pages/{id}/compounds/analyze-box — the models read, the human draws."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from application.dtos.page_dtos import PageResponse
from application.ports.blob_store import BlobStore
from application.ports.cser_service import CserService
from application.ports.repositories.page_read_models import PageReadModel
from application.use_cases.storage_keys import cser_render_key
from interfaces.api.main import app
from interfaces.dependencies import get_auth, get_container
from tests.conftest import strip_authz_middleware
from tests.fakes.fake_auth import FakeAuth
from tests.mocks import MockCserService

PAGE_ID = UUID("44444444-4444-4444-4444-444444444444")
ARTIFACT_ID = UUID("55555555-5555-5555-5555-555555555555")
RENDER_KEY = cser_render_key(ARTIFACT_ID, 7)
URL = f"/pages/{PAGE_ID}/compounds/analyze-box"


class FakePageReadModel:
    async def get_page_by_id(self, page_id, workspace_id=None):
        return PageResponse(
            page_id=page_id,
            artifact_id=ARTIFACT_ID,
            name="p7",
            index=7,
            compound_mentions=[],
        )


class FakeBlobStore:
    def __init__(self, *, has_render: bool = True) -> None:
        self._keys = {RENDER_KEY} if has_render else set()

    def exists(self, key: str) -> bool:
        return key in self._keys


class FakeContainer:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]


def _client(cser, *, has_render: bool = True, actions=None) -> TestClient:
    strip_authz_middleware(app)
    app.dependency_overrides[get_container] = lambda: FakeContainer(
        {
            PageReadModel: FakePageReadModel(),
            BlobStore: FakeBlobStore(has_render=has_render),
            CserService: cser,
        },
    )
    app.dependency_overrides[get_auth] = lambda: FakeAuth(
        role="editor", user_id=uuid4(), workspace_id=uuid4(), actions=actions,
    )
    return TestClient(app)


def _post(body, **kwargs):
    cser = kwargs.pop("cser", None) or MockCserService()
    try:
        return _client(cser, **kwargs).post(URL, json=body), cser
    finally:
        app.dependency_overrides.clear()


def test_structure_box_only_returns_a_smiles_and_no_label():
    resp, cser = _post({"structure_bbox": [10, 20, 110, 220]})

    assert resp.status_code == 200
    assert resp.json() == {"smiles": "CCO", "label_text": None}
    assert cser.analyze_calls == [
        {"render_key": RENDER_KEY, "structure_bbox": [10, 20, 110, 220], "label_bbox": None},
    ]


def test_label_box_only_returns_text_and_no_smiles():
    resp, cser = _post({"label_bbox": [10, 230, 60, 250]})

    assert resp.status_code == 200
    assert resp.json() == {"smiles": None, "label_text": "1a"}
    assert cser.analyze_calls[0]["structure_bbox"] is None


def test_both_boxes_return_both_reads():
    resp, _ = _post({"structure_bbox": [1, 2, 3, 4], "label_bbox": [5, 6, 7, 8]})

    assert resp.json() == {"smiles": "CCO", "label_text": "1a"}


def test_empty_body_is_the_warm_up_call_and_still_reaches_the_service():
    # Both null loads the pipeline while the user is drawing. Keep it.
    resp, cser = _post({})

    assert resp.status_code == 200
    assert resp.json() == {"smiles": None, "label_text": None}
    assert cser.analyze_calls == [
        {"render_key": RENDER_KEY, "structure_bbox": None, "label_bbox": None},
    ]


def test_missing_cser_render_is_a_404():
    resp, cser = _post({"structure_bbox": [1, 2, 3, 4]}, has_render=False)

    assert resp.status_code == 404
    assert cser.analyze_calls == []


def test_unreadable_structure_is_a_200_with_a_null_smiles():
    class UnreadableCser(MockCserService):
        def analyze_boxes(self, render_key, structure_bbox, label_bbox):
            super().analyze_boxes(render_key, structure_bbox, label_bbox)
            return None, None

    resp, _ = _post({"structure_bbox": [1, 2, 3, 4]}, cser=UnreadableCser())

    assert resp.status_code == 200
    assert resp.json() == {"smiles": None, "label_text": None}


def test_hiledit_action_is_required():
    resp, cser = _post({"structure_bbox": [1, 2, 3, 4]}, actions=set())

    assert resp.status_code == 403
    assert cser.analyze_calls == []


def test_a_malformed_box_is_rejected_before_any_model_runs():
    resp, cser = _post({"structure_bbox": [1, 2, 3]})

    assert resp.status_code == 422
    assert cser.analyze_calls == []
