from pydantic import BaseModel


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
