from __future__ import annotations

import structlog

from application.ports.smiles_validator import SmilesValidator

logger = structlog.get_logger()


class RdkitSmilesValidator(SmilesValidator):
    """SMILES validation and canonicalization using RDKit.

    RDKit is lazy-imported on first call to avoid paying the import cost
    in processes that don't perform compound extraction.
    """

    def validate(self, smiles: str) -> bool:
        """Return True if RDKit can parse the SMILES string."""
        from rdkit import Chem  # lazy import — rdkit is heavy

        return Chem.MolFromSmiles(smiles) is not None

    def canonicalize(self, smiles: str) -> str | None:
        """Return canonical SMILES, or None if the input is invalid."""
        from rdkit import Chem  # lazy import — rdkit is heavy

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol)
