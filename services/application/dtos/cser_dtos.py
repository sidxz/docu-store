from typing import Annotated

from pydantic import BaseModel, Field


class CserCompoundResult(BaseModel):
    """Raw output from the CserService before domain mapping.

    Represents one structure-label pair returned by ChemPipeline.process().
    Bounding boxes are pixels of the page's persisted CSER render.
    """

    smiles: str | None
    label_text: str | None
    match_confidence: float | None
    structure_bbox: list[int] | None = None
    label_bbox: list[int] | None = None
    structure_confidence: float | None = None
    label_confidence: float | None = None


Bbox = Annotated[list[float], Field(min_length=4, max_length=4)]


class AnalyzeCompoundBoxRequest(BaseModel):
    """Human-drawn boxes to read, in pixels of the page's CSER render."""

    structure_bbox: Bbox | None = Field(
        default=None,
        description="[x1, y1, x2, y2] to read a SMILES from; omit to skip OCSR.",
    )
    label_bbox: Bbox | None = Field(
        default=None,
        description="[x1, y1, x2, y2] to read caption text from; omit to skip OCR.",
    )


class AnalyzeCompoundBoxResponse(BaseModel):
    """What the models read. Null means 'not asked' or 'could not read'."""

    smiles: str | None = None
    label_text: str | None = None
