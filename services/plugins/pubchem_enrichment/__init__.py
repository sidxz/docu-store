"""PubChem enrichment plugin — fetches compound identifiers from PubChem PUG REST API."""

from plugins.pubchem_enrichment.plugin import PubChemEnrichmentPlugin

plugin = PubChemEnrichmentPlugin()

__all__ = ["plugin"]
