"""Browser-based OAuth login for docu-store CLI.

Flow:
1. Start local HTTP server on a random port
2. Open browser to Sentinel's IdP OAuth proxy (e.g., GitHub)
3. User authenticates, Sentinel redirects back with IdP token in URL hash
4. Local callback page extracts token via JS and POSTs to local server
5. CLI calls /authz/resolve to get authz token
6. Credentials stored locally
"""

from __future__ import annotations

import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.cli.auth import CliAuth

# HTML served at the callback URL — extracts hash fragment and POSTs to local server
CALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>docu-store login</title></head>
<body>
<p id="status">Completing login...</p>
<script>
const hash = window.location.hash.substring(1);
const params = new URLSearchParams(hash);
const token = params.get('id_token');
const nonce = params.get('nonce');
if (token) {
  fetch('/token', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token: token, nonce: nonce})
  }).then(() => {
    document.getElementById('status').textContent = 'Login successful! You can close this tab.';
  }).catch(() => {
    document.getElementById('status').textContent = 'Login failed. Please try again.';
  });
} else {
  document.getElementById('status').textContent = 'No token received. Please try again.';
}
</script>
</body></html>"""


def browser_login(
    auth: CliAuth,
    provider: str,
    workspace_id: str,
) -> None:
    """Run the browser OAuth login flow."""
    nonce = secrets.token_urlsafe(16)
    captured: dict = {}
    server_ready = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            """Serve the callback HTML page."""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(CALLBACK_HTML.encode())

        def do_POST(self):
            """Receive the IdP token from the callback page's JS."""
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))

            if body.get("nonce") != nonce:
                self.send_response(400)
                self.end_headers()
                return

            captured["idp_token"] = body["token"]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, format, *args):
            pass  # Suppress request logs

    # Start local server on random port
    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    callback_url = f"http://localhost:{port}/callback"

    def serve():
        server_ready.set()
        while "idp_token" not in captured:
            server.handle_request()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server_ready.wait()

    # Open browser to Sentinel's OAuth proxy
    login_url = (
        f"{auth.sentinel_url}/authz/idp/{provider}/login?redirect_uri={callback_url}&nonce={nonce}"
    )
    print(f"Opening browser for {provider} login...")
    print(f"If the browser doesn't open, visit: {login_url}")
    webbrowser.open(login_url)

    # Wait for callback (timeout after 5 minutes)
    thread.join(timeout=300)
    server.server_close()

    if "idp_token" not in captured:
        print("Login timed out.", file=sys.stderr)
        sys.exit(1)

    # Exchange IdP token for authz token
    print("Authenticating with Sentinel...")
    try:
        data = auth.resolve_authz(captured["idp_token"], provider, workspace_id)
    except Exception as e:
        print(f"Login failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not data.get("authz_token"):
        print("No authz token received. Check workspace_id.", file=sys.stderr)
        sys.exit(1)

    auth.save_login(
        idp_token=captured["idp_token"],
        provider=provider,
        workspace_id=workspace_id,
        authz_token=data["authz_token"],
        expires_in=data["expires_in"],
        user_email=data.get("user", {}).get("email"),
        workspace_slug=data.get("workspace", {}).get("slug"),
    )

    email = data.get("user", {}).get("email", "unknown")
    slug = data.get("workspace", {}).get("slug", workspace_id)
    print(f"Logged in as {email} (workspace: {slug})")


def token_login(auth: CliAuth, token: str, workspace_id: str) -> None:
    """Login by pasting an existing authz token directly."""
    auth.save_login(
        idp_token="",  # No IdP token — can't auto-refresh
        provider="manual",
        workspace_id=workspace_id,
        authz_token=token,
        expires_in=300,  # Assume 5 min, will fail on expiry
    )
    print("Token saved. Note: auto-refresh is not available with manual tokens.")
    print("When the token expires, run 'docu-store login' with --browser for persistent auth.")
