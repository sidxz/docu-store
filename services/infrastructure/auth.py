import structlog
from duar_auth import Duar

from infrastructure.config import settings

logger = structlog.get_logger()

# RBAC action definitions for this service. Registered best-effort at startup
# (see register_service_actions) rather than via the Duar(actions=...) ctor:
# the SDK lifespan registers ctor actions synchronously and fatally, so a slow
# or down Duar would block boot for a rarely-changing housekeeping call.
SERVICE_ACTIONS = [
    {"action": "artifacts:create", "description": "Create artifacts"},
    {"action": "artifacts:delete", "description": "Delete artifacts"},
    {"action": "artifacts:export", "description": "Export artifacts"},
    {
        "action": "artifacts:hiledit",
        "description": "Human-in-the-loop correction of extracted metadata",
    },
]

duar = Duar(
    base_url=settings.duar_url,
    service_name=settings.duar_service_name,
    service_key=settings.duar_service_key,
    mode="authz",
    idp_jwks_url=settings.duar_idp_jwks_url,
    idp_audience=settings.duar_idp_audience,
    idp_issuer=settings.duar_idp_issuer or None,
    cache_ttl=settings.duar_cache_ttl,
)


async def register_service_actions(duar: Duar) -> bool:
    """Register SERVICE_ACTIONS with Duar, best-effort, at startup.

    Action defs change rarely and aren't needed to serve requests, so a transient
    Duar outage must never block boot. On failure we log and continue; the
    next successful startup re-registers. Returns True iff registration succeeded.
    """
    try:
        await duar.roles.register_actions(SERVICE_ACTIONS)
    except Exception:
        logger.exception("duar_actions_register_failed", action_count=len(SERVICE_ACTIONS))
        return False
    logger.info("duar_actions_registered", action_count=len(SERVICE_ACTIONS))
    return True
