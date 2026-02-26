from typing import Protocol


class SmilesValidator(Protocol):
    """Port for validating and normalizing SMILES chemical structure strings.

    Abstracts the chemistry library (RDKit, etc.) from the application layer.
    Implementations are expected to be stateless and fast — no model loading.
    """

    def validate(self, smiles: str) -> bool:
        """Return True if the SMILES string represents a parseable chemical structure."""
        ...

    def canonicalize(self, smiles: str) -> str | None:
        """Return the canonical SMILES for the given input, or None if invalid."""
        ...
