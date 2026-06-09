"""Auth routes — BFF mint endpoint for non-browser clients (the CLI).

Since Sentinel 0.11.0, minting an authz token requires a service key, which must
not be distributed to CLI users. The CLI POSTs its IdP token here; this route
forwards to Sentinel's /authz/resolve with the service key and returns the result.

This route is the pre-auth credential-issuance step, so it is excluded from the
AuthzMiddleware in main.py. It is gated by Sentinel's own IdP-token validation.

Request body (from the CLI): { idp_token, provider, workspace_id, nonce? }
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from infrastructure.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/mint")
async def mint_authz_token(request: Request) -> JSONResponse:
    """Forward an authz-token mint request to Sentinel with the service key."""
    if not settings.sentinel_service_key:
        return JSONResponse(
            {"detail": "Mint endpoint not configured: SENTINEL_SERVICE_KEY missing."},
            status_code=503,
        )

    body = await request.json()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.sentinel_url.rstrip('/')}/authz/resolve",
            headers={"X-Service-Key": settings.sentinel_service_key},
            json=body,
        )

    try:
        data = resp.json()
    except ValueError:
        data = {"detail": resp.text or "Token mint failed"}
    return JSONResponse(content=data, status_code=resp.status_code)
