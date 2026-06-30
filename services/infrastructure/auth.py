import structlog
from sentinel_auth import Sentinel

from infrastructure.config import settings

logger = structlog.get_logger()

# RBAC action definitions for this service. Registered best-effort at startup
# (see register_service_actions) rather than via the Sentinel(actions=...) ctor:
# the SDK lifespan registers ctor actions synchronously and fatally, so a slow
# or down Sentinel would block boot for a rarely-changing housekeeping call.
SERVICE_ACTIONS = [
    {"action": "artifacts:create", "description": "Create artifacts"},
    {"action": "artifacts:delete", "description": "Delete artifacts"},
    {"action": "artifacts:export", "description": "Export artifacts"},
]

sentinel = Sentinel(
    base_url=settings.sentinel_url,
    service_name=settings.sentinel_service_name,
    service_key=settings.sentinel_service_key,
    mode="authz",
    idp_jwks_url=settings.sentinel_idp_jwks_url,
    idp_audience=settings.sentinel_idp_audience,
    idp_issuer=settings.sentinel_idp_issuer or None,
    cache_ttl=settings.sentinel_cache_ttl,
)


async def register_service_actions(sentinel: Sentinel) -> bool:
    """Register SERVICE_ACTIONS with Sentinel, best-effort, at startup.

    Action defs change rarely and aren't needed to serve requests, so a transient
    Sentinel outage must never block boot. On failure we log and continue; the
    next successful startup re-registers. Returns True iff registration succeeded.
    """
    try:
        await sentinel.roles.register_actions(SERVICE_ACTIONS)
    except Exception:
        logger.exception("sentinel_actions_register_failed", action_count=len(SERVICE_ACTIONS))
        return False
    logger.info("sentinel_actions_registered", action_count=len(SERVICE_ACTIONS))
    return True
