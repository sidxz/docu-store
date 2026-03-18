"""PubChem PUG REST API client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class PubChemCompoundInfo:
    """Result of a PubChem lookup for a single SMILES."""

    canonical_smiles: str
    pubchem_cid: int | None = None
    iupac_name: str | None = None
    molecular_formula: str | None = None
    molecular_weight: float | None = None
    inchi: str | None = None
    inchi_key: str | None = None
    status: str = "success"  # "success" | "not_found" | "error"
    error_message: str | None = None


_PROPERTIES = "IUPACName,MolecularFormula,MolecularWeight,InChI,InChIKey"


class PubChemClient:
    """Async client for the PubChem PUG REST API."""

    def __init__(
        self,
        base_url: str = "https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        rate_limit_per_second: float = 5.0,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._interval = 1.0 / rate_limit_per_second
        self._timeout = timeout_seconds
        self._last_request: float = 0.0

    async def _rate_limit(self) -> None:
        """Simple rate limiter — wait if we're calling too fast."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        if elapsed < self._interval:
            await asyncio.sleep(self._interval - elapsed)
        self._last_request = asyncio.get_event_loop().time()

    async def lookup_smiles(self, smiles: str) -> PubChemCompoundInfo:
        """Look up a single SMILES in PubChem and return compound info."""
        try:
            import httpx  # noqa: PLC0415
        except ImportError:
            return PubChemCompoundInfo(
                canonical_smiles=smiles,
                status="error",
                error_message="httpx not installed",
            )

        await self._rate_limit()

        encoded = quote(smiles, safe="")
        url = f"{self.base_url}/compound/smiles/{encoded}/property/{_PROPERTIES}/JSON"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)

            if response.status_code == 404:
                return PubChemCompoundInfo(canonical_smiles=smiles, status="not_found")

            response.raise_for_status()
            data = response.json()

            props = data.get("PropertyTable", {}).get("Properties", [{}])[0]
            return PubChemCompoundInfo(
                canonical_smiles=smiles,
                pubchem_cid=props.get("CID"),
                iupac_name=props.get("IUPACName"),
                molecular_formula=props.get("MolecularFormula"),
                molecular_weight=props.get("MolecularWeight"),
                inchi=props.get("InChI"),
                inchi_key=props.get("InChIKey"),
                status="success",
            )

        except Exception as e:
            logger.warning("pubchem_lookup_error", smiles=smiles, error=str(e))
            return PubChemCompoundInfo(
                canonical_smiles=smiles,
                status="error",
                error_message=str(e),
            )

    async def lookup_batch(self, smiles_list: list[str]) -> list[PubChemCompoundInfo]:
        """Look up multiple SMILES sequentially with rate limiting."""
        results: list[PubChemCompoundInfo] = []
        for smiles in smiles_list:
            results.append(await self.lookup_smiles(smiles))
        return results
