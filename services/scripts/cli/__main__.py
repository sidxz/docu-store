"""docu-store CLI — login and bulk upload documents.

Usage:
    uv run python -m scripts.cli login --provider github --workspace <workspace-id>
    uv run python -m scripts.cli login --token <paste-token> --workspace <workspace-id>
    uv run python -m scripts.cli upload /path/to/pdfs
    uv run python -m scripts.cli upload /path/to/pdfs --recursive --resume
    uv run python -m scripts.cli logout
    uv run python -m scripts.cli whoami
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from scripts.cli.auth import CREDENTIALS_FILE, AuthError, CliAuth


def _get_auth(args: argparse.Namespace) -> CliAuth:
    sentinel_url = args.sentinel_url or os.environ.get("SENTINEL_URL", "http://localhost:8100")
    service_key = args.service_key or os.environ.get("SENTINEL_SERVICE_KEY", "")
    if not service_key:
        print("Error: provide --service-key or set SENTINEL_SERVICE_KEY", file=sys.stderr)
        sys.exit(1)
    return CliAuth(sentinel_url=sentinel_url, service_key=service_key)


def cmd_login(args: argparse.Namespace) -> None:
    auth = _get_auth(args)

    if args.token:
        # Manual token paste
        if not args.workspace:
            print("Error: --workspace is required", file=sys.stderr)
            sys.exit(1)
        from scripts.cli.login import token_login

        token_login(auth, args.token, args.workspace)
    else:
        # Browser OAuth flow
        if not args.workspace:
            print("Error: --workspace is required", file=sys.stderr)
            sys.exit(1)
        from scripts.cli.login import browser_login

        browser_login(auth, args.provider, args.workspace)


def cmd_logout(args: argparse.Namespace) -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        print("Logged out.")
    else:
        print("Not logged in.")


def cmd_whoami(args: argparse.Namespace) -> None:
    auth = _get_auth(args)
    if not auth.is_logged_in():
        print("Not logged in. Run: docu-store login")
        sys.exit(1)
    creds = auth._creds
    print(f"Email:     {creds.get('user_email', 'unknown')}")
    print(f"Workspace: {creds.get('workspace_slug', creds.get('workspace_id', 'unknown'))}")
    print(f"Provider:  {creds.get('provider', 'unknown')}")


def cmd_upload(args: argparse.Namespace) -> None:
    auth = _get_auth(args)
    if not auth.is_logged_in():
        print("Not logged in. Run: docu-store login", file=sys.stderr)
        sys.exit(1)

    from scripts.cli.upload import upload_directory

    try:
        upload_directory(
            auth=auth,
            directory=Path(args.directory),
            api_url=args.api_url,
            artifact_type=args.artifact_type,
            visibility=args.visibility,
            delay=args.delay,
            dry_run=args.dry_run,
            resume=args.resume,
            recursive=args.recursive,
        )
    except AuthError as e:
        print(f"\nAuth error: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="docu-store",
        description="docu-store CLI — manage documents from the command line",
    )
    parser.add_argument("--sentinel-url", help="Sentinel URL (or SENTINEL_URL env)")
    parser.add_argument("--service-key", help="Sentinel service key (or SENTINEL_SERVICE_KEY env)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # login
    login_parser = subparsers.add_parser("login", help="Authenticate with Sentinel")
    login_parser.add_argument("--provider", default="github", help="IdP provider (default: github)")
    login_parser.add_argument("--workspace", required=True, help="Workspace ID to authorize for")
    login_parser.add_argument("--token", help="Paste an existing authz token (skips browser flow)")
    login_parser.set_defaults(func=cmd_login)

    # logout
    logout_parser = subparsers.add_parser("logout", help="Remove stored credentials")
    logout_parser.set_defaults(func=cmd_logout)

    # whoami
    whoami_parser = subparsers.add_parser("whoami", help="Show current auth status")
    whoami_parser.set_defaults(func=cmd_whoami)

    # upload
    upload_parser = subparsers.add_parser("upload", help="Upload PDFs from a directory")
    upload_parser.add_argument("directory", type=str, help="Directory containing PDF files")
    upload_parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    upload_parser.add_argument("--artifact-type", default="RESEARCH_ARTICLE", help="Artifact type")
    upload_parser.add_argument(
        "--visibility", default="workspace", help="Visibility (workspace/private)",
    )
    upload_parser.add_argument("--delay", type=float, default=2.0, help="Seconds between uploads")
    upload_parser.add_argument(
        "--dry-run", action="store_true", help="List files without uploading",
    )
    upload_parser.add_argument("--resume", action="store_true", help="Skip already-uploaded files")
    upload_parser.add_argument("--recursive", "-r", action="store_true", help="Scan subdirectories")
    upload_parser.set_defaults(func=cmd_upload)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
