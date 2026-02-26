from pydantic import BaseModel


class CserCompoundResult(BaseModel):
    """Raw output from the CserService before domain mapping.

    Represents one structure-label pair returned by ChemPipeline.process().
    Fields map directly from CompoundPair attributes.
    """

    smiles: str | None
    label_text: str | None
    match_confidence: float | None
