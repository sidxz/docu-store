"""PubChem plugin configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PubChemPluginSettings(BaseSettings):
    """Configuration for the PubChem enrichment plugin.

    All env vars are prefixed with PLUGIN_PUBCHEM_.
    """

    model_config = SettingsConfigDict(
        env_prefix="PLUGIN_PUBCHEM_",
        case_sensitive=False,
        extra="ignore",
    )

    api_base_url: str = Field(
        default="https://pubchem.ncbi.nlm.nih.gov/rest/pug",
        description="PubChem PUG REST API base URL.",
    )
    rate_limit_per_second: float = Field(
        default=5.0,
        description="Max requests per second to PubChem API.",
    )
    batch_size: int = Field(
        default=10,
        description="Number of SMILES to enrich per batch call.",
    )
    timeout_seconds: int = Field(
        default=30,
        description="HTTP request timeout in seconds.",
    )
