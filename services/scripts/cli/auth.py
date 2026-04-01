"""Credential management and auto-refresh for docu-store CLI.

Stores credentials in ~/.config/docu-store/credentials.json.
Refreshes authz tokens transparently via /authz/resolve using the stored IdP token.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

CREDENTIALS_DIR = Path.home() / ".config" / "docu-store"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
REFRESH_BUFFER_SECONDS = 30


class AuthError(Exception):
    pass


class CliAuth:
    """Manages Sentinel authz token lifecycle for CLI tools.

    Auth flow:
    1. Login captures an IdP token (e.g., GitHub access token) and workspace info.
    2. Calls /authz/resolve to get a short-lived authz token.
    3. On expiry, calls /authz/resolve again with the same IdP token (GitHub tokens don't expire).
    """

    def __init__(self, sentinel_url: str, service_key: str) -> None:
        self.sentinel_url = sentinel_url.rstrip("/")
        self.service_key = service_key
        self._creds: dict | None = None
        self._load()

    def is_logged_in(self) -> bool:
        return self._creds is not None and "idp_token" in self._creds

    def get_token(self) -> str:
        """Return a valid authz token, refreshing via /authz/resolve if expired."""
        if not self.is_logged_in():
            raise AuthError("Not logged in. Run: docu-store login")

        if self._is_expired():
            self._refresh()

        return self._creds["authz_token"]

    def get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}

    def save_login(
        self,
        idp_token: str,
        provider: str,
        workspace_id: str,
        authz_token: str,
        expires_in: int,
        user_email: str | None = None,
        workspace_slug: str | None = None,
    ) -> None:
        """Store credentials from a successful login."""
        self._creds = {
            "idp_token": idp_token,
            "provider": provider,
            "workspace_id": workspace_id,
            "authz_token": authz_token,
            "expires_at": time.time() + expires_in,
            "user_email": user_email,
            "workspace_slug": workspace_slug,
        }
        self._save()

    def logout(self) -> None:
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
        self._creds = None

    def resolve_authz(self, idp_token: str, provider: str, workspace_id: str) -> dict:
        """Call /authz/resolve and return the response."""
        resp = httpx.post(
            f"{self.sentinel_url}/authz/resolve",
            json={
                "idp_token": idp_token,
                "provider": provider,
                "workspace_id": workspace_id,
            },
            headers={"X-Service-Key": self.service_key},
            timeout=30,
        )
        if resp.status_code == 400:
            raise AuthError(f"IdP token rejected: {resp.json().get('detail', resp.text)}")
        if resp.status_code == 403:
            raise AuthError(f"Access denied: {resp.json().get('detail', resp.text)}")
        resp.raise_for_status()
        return resp.json()

    def _is_expired(self) -> bool:
        expires_at = self._creds.get("expires_at", 0)
        return time.time() > expires_at - REFRESH_BUFFER_SECONDS

    def _refresh(self) -> None:
        """Re-resolve authz token using stored IdP token."""
        try:
            data = self.resolve_authz(
                self._creds["idp_token"],
                self._creds["provider"],
                self._creds["workspace_id"],
            )
        except AuthError:
            raise AuthError(
                "Session expired — your IdP token may have been revoked. Run: docu-store login",
            )

        self._creds["authz_token"] = data["authz_token"]
        self._creds["expires_at"] = time.time() + data["expires_in"]
        self._save()

    def _load(self) -> None:
        if CREDENTIALS_FILE.exists():
            try:
                self._creds = json.loads(CREDENTIALS_FILE.read_text())
            except (json.JSONDecodeError, KeyError):
                self._creds = None

    def _save(self) -> None:
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_FILE.write_text(json.dumps(self._creds, indent=2))
        CREDENTIALS_FILE.chmod(0o600)
