"""The training export: byte-identical images, verbatim coordinates."""

from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from PIL import Image

from application.use_cases.cser_export_use_case import build_cser_export_zip, yolo_line
from application.use_cases.storage_keys import cser_render_key

WORKSPACE = UUID("44444444-4444-4444-4444-444444444444")
EXPORTED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeBlobStore:
    def __init__(self, keys: dict[str, bytes]) -> None:
        self.keys = keys

    def exists(self, key: str) -> bool:
        return key in self.keys

    def get_bytes(self, key: str) -> bytes:
        return self.keys[key]


def _page(page_id, artifact_id, index, mentions):
    return {
        "page_id": str(page_id),
        "artifact_id": str(artifact_id),
        "index": index,
        "compound_mentions": mentions,
        "human_corrections": {
            "compound_mentions": {
                "corrected_by_id": "u1",
                "corrected_by_name": "Reviewer",
                "corrected_at": EXPORTED_AT,
            }
        },
    }


def test_yolo_line_normalizes_against_the_image_it_ships_with():
    # Box [10, 20, 110, 220] on a 1000x2000 image:
    # cx = 60/1000 = 0.06, cy = 120/2000 = 0.06, w = 100/1000 = 0.1, h = 200/2000 = 0.1
    assert yolo_line(0, [10, 20, 110, 220], 1000, 2000) == "0 0.060000 0.060000 0.100000 0.100000"


def test_export_layout_and_verbatim_coordinates():
    page_id, artifact_id = uuid4(), uuid4()
    mentions = [
        {
            "smiles": "CCO",
            "extracted_id": "1a",
            "structure_bbox": [10, 20, 110, 220],
            "label_bbox": [10, 230, 60, 250],
        },
        {
            "smiles": "CCC",
            "extracted_id": None,
            "structure_bbox": [300, 400, 500, 600],
            "label_bbox": None,
        },
    ]
    image_bytes = _png(1000, 2000)
    blob = FakeBlobStore({cser_render_key(artifact_id, 3): image_bytes})

    raw = build_cser_export_zip(
        [_page(page_id, artifact_id, 3, mentions)], blob, WORKSPACE, EXPORTED_AT
    )

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        names = set(zf.namelist())
        assert f"images/{page_id}.png" in names
        assert f"ground_truth/{page_id}.json" in names
        assert f"labels/{page_id}.txt" in names
        assert "manifest.json" in names

        # The image is the stored render, not a re-render.
        assert zf.read(f"images/{page_id}.png") == image_bytes

        ground_truth = json.loads(zf.read(f"ground_truth/{page_id}.json"))
        assert ground_truth == [
            {
                "struct_bbox": [10, 20, 110, 220],
                "label_bbox": [10, 230, 60, 250],
                "label_text": "1a",
                "smiles": "CCO",
            },
            {
                "struct_bbox": [300, 400, 500, 600],
                "label_bbox": None,
                "label_text": "",
                "smiles": "CCC",
            },
        ]

        # class 0 = chemical_structure, class 1 = compound_label; the
        # unlabelled pair contributes a structure line only.
        lines = zf.read(f"labels/{page_id}.txt").decode().strip().split("\n")
        assert [line.split()[0] for line in lines] == ["0", "1", "0"]


def test_a_reviewed_empty_page_exports_an_empty_ground_truth_and_no_label_file():
    page_id, artifact_id = uuid4(), uuid4()
    blob = FakeBlobStore({cser_render_key(artifact_id, 0): _png(100, 100)})

    raw = build_cser_export_zip([_page(page_id, artifact_id, 0, [])], blob, WORKSPACE, EXPORTED_AT)

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        assert json.loads(zf.read(f"ground_truth/{page_id}.json")) == []
        assert f"images/{page_id}.png" in zf.namelist()
        # YOLO convention: no label file rather than an empty one.
        assert f"labels/{page_id}.txt" not in zf.namelist()


def test_a_page_without_a_stored_render_is_skipped_and_reported():
    page_id, artifact_id = uuid4(), uuid4()
    mentions = [{"smiles": "CCO", "extracted_id": "1a", "structure_bbox": [1, 2, 3, 4], "label_bbox": None}]

    raw = build_cser_export_zip(
        [_page(page_id, artifact_id, 7, mentions)], FakeBlobStore({}), WORKSPACE, EXPORTED_AT
    )

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        assert f"images/{page_id}.png" not in zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["skipped"] == [{"page_id": str(page_id), "reason": "no CSER render stored"}]
        assert manifest["pages"] == []


def test_mentions_without_coordinates_are_left_out_of_ground_truth():
    page_id, artifact_id = uuid4(), uuid4()
    mentions = [
        {"smiles": "CCO", "extracted_id": "1a", "structure_bbox": None, "label_bbox": None},
        {"smiles": "CCC", "extracted_id": "2b", "structure_bbox": [1, 2, 3, 4], "label_bbox": None},
    ]
    blob = FakeBlobStore({cser_render_key(artifact_id, 0): _png(100, 100)})

    raw = build_cser_export_zip([_page(page_id, artifact_id, 0, mentions)], blob, WORKSPACE, EXPORTED_AT)

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        ground_truth = json.loads(zf.read(f"ground_truth/{page_id}.json"))
        assert [g["smiles"] for g in ground_truth] == ["CCC"]


def test_source_filename_comes_from_the_artifact_filenames_map_not_the_page():
    """Page docs have no `artifact_name` field; the real filename lives on the
    artifact document and is passed in as a lookup map keyed by artifact_id.
    """
    page_id, artifact_id = uuid4(), uuid4()
    blob = FakeBlobStore({cser_render_key(artifact_id, 0): _png(10, 10)})

    raw = build_cser_export_zip(
        [_page(page_id, artifact_id, 0, [])],
        blob,
        WORKSPACE,
        EXPORTED_AT,
        artifact_filenames={str(artifact_id): "compounds.pdf"},
    )

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["pages"][0]["source_filename"] == "compounds.pdf"


def test_source_filename_is_none_when_the_map_has_no_entry():
    page_id, artifact_id = uuid4(), uuid4()
    blob = FakeBlobStore({cser_render_key(artifact_id, 0): _png(10, 10)})

    raw = build_cser_export_zip([_page(page_id, artifact_id, 0, [])], blob, WORKSPACE, EXPORTED_AT)

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["pages"][0]["source_filename"] is None


def test_a_page_whose_mentions_all_lack_coordinates_is_skipped_not_exported_as_empty():
    # An empty ground_truth is a *claim*: "a human confirmed there are no
    # structures here". A page whose mentions merely predate coordinates must
    # not make that claim — it would train the detector to miss real structures.
    page_id, artifact_id = uuid4(), uuid4()
    mentions = [{"smiles": "CCO", "extracted_id": "1a", "structure_bbox": None, "label_bbox": None}]
    blob = FakeBlobStore({cser_render_key(artifact_id, 0): _png(100, 100)})

    raw = build_cser_export_zip([_page(page_id, artifact_id, 0, mentions)], blob, WORKSPACE, EXPORTED_AT)

    with zipfile.ZipFile(BytesIO(raw)) as zf:
        names = zf.namelist()
        assert f"ground_truth/{page_id}.json" not in names
        assert f"images/{page_id}.png" not in names
        assert f"labels/{page_id}.txt" not in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["skipped"] == [
            {"page_id": str(page_id), "reason": "mentions have no coordinates"}
        ]
        assert manifest["pages"] == []
