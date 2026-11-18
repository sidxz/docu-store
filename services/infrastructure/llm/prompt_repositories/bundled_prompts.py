"""The prompts shipped with this release, as Langfuse templates.

``default_prompts/*.yaml`` is the source of truth. Langfuse gets a copy of them
(``langfuse_prompt_sync``), and the Langfuse repository falls back to them when
Langfuse cannot serve a prompt.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import yaml

DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "default_prompts"


def load_bundled_prompts(prompts_dir: Path = DEFAULT_PROMPTS_DIR) -> dict[str, str]:
    """Prompt name → template in Langfuse's ``{{variable}}`` syntax.

    The YAML files use Python's ``{variable}`` placeholders.
    """
    prompts = {}
    for path in sorted(prompts_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        prompts[data["name"]] = re.sub(r"\{(\w+)\}", r"{{\1}}", data["template"].rstrip())
    return prompts


@cache
def bundled_prompts() -> dict[str, str]:
    """The prompts in ``DEFAULT_PROMPTS_DIR``, read once per process."""
    return load_bundled_prompts()
