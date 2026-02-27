#!/usr/bin/env python3
"""Seed Langfuse with prompts from YAML files.

Run after `make docker-up` to push all default prompts so the app works
immediately without any manual Langfuse UI steps.

Templates are stored as Langfuse text prompts using {{variable}} Mustache syntax
(converted from the {variable} Python format used in the YAML source files).
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import yaml

PROMPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "infrastructure"
    / "llm"
    / "default_prompts"
)

LANGFUSE_HOST = "http://localhost:3000"
LANGFUSE_PUBLIC_KEY = "pk-lf-docu-store-dev"
LANGFUSE_SECRET_KEY = "sk-lf-docu-store-dev"


def _to_mustache(template: str) -> str:
    """Convert Python {variable} placeholders to Langfuse {{variable}} Mustache syntax."""
    return re.sub(r"\{(\w+)\}", r"{{\1}}", template)


def _wait_for_langfuse(client: object, max_retries: int = 30) -> None:
    for attempt in range(1, max_retries + 1):
        try:
            client.auth_check()  # type: ignore[attr-defined]
            print("✅ Langfuse is ready")
            return
        except Exception:  # noqa: BLE001
            print(f"   Waiting for Langfuse... ({attempt}/{max_retries})")
            time.sleep(3)
    print("❌ Langfuse did not become ready in time", file=sys.stderr)
    sys.exit(1)


def seed() -> None:
    try:
        from langfuse import Langfuse  # noqa: PLC0415
    except ImportError:
        print("❌ langfuse package not installed — run `uv sync`", file=sys.stderr)
        sys.exit(1)

    client = Langfuse(
        host=LANGFUSE_HOST,
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
    )

    _wait_for_langfuse(client)

    yaml_files = sorted(PROMPTS_DIR.glob("*.yaml"))
    if not yaml_files:
        print(f"⚠️  No YAML prompt files found in {PROMPTS_DIR}")
        return

    for yaml_path in yaml_files:
        with yaml_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        name: str = data["name"]
        template: str = _to_mustache(data["template"].rstrip())

        try:
            client.create_prompt(
                name=name,
                prompt=template,
                labels=["production"],
                type="text",
            )
            print(f"✅ Seeded prompt: {name}")
        except Exception as exc:  # noqa: BLE001
            # create_prompt raises if the exact content already exists in some SDK versions;
            # on a fresh DB this should always succeed.
            print(f"⚠️  Skipped '{name}': {exc}")

    print("\nDone — all prompts available at http://localhost:3000")


if __name__ == "__main__":
    seed()
