from sentinel_auth import Sentinel

from infrastructure.config import settings

sentinel = Sentinel(
    base_url=settings.sentinel_url,
    service_name=settings.sentinel_service_name,
    service_key=settings.sentinel_service_key,
    mode="authz",
    idp_jwks_url=settings.sentinel_idp_jwks_url,
    idp_audience=settings.sentinel_idp_audience,
    idp_issuer=settings.sentinel_idp_issuer or None,
    cache_ttl=settings.sentinel_cache_ttl,
    actions=[
        {"action": "artifacts:create", "description": "Create artifacts"},
        {"action": "artifacts:delete", "description": "Delete artifacts"},
        {"action": "artifacts:export", "description": "Export artifacts"},
    ],
)
