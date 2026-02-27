from __future__ import annotations

from pathlib import Path

import structlog
import yaml

log = structlog.get_logger(__name__)

_DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "default_prompts"


class YamlPromptRepository:
    """PromptRepositoryPort adapter that reads prompts from YAML files.

    Used during development when Langfuse is not running, or as a fallback.
    Set PROMPT_REPOSITORY_TYPE=yaml to activate.

    Files are read from infrastructure/llm/default_prompts/{name}.yaml.
    The `version` parameter is ignored — the file on disk is always returned.
    """

    def __init__(self, prompts_dir: Path = _DEFAULT_PROMPTS_DIR) -> None:
        self._dir = prompts_dir
        self._cache: dict[str, str] = {}  # name → raw template string

    async def render_prompt(
        self,
        name: str,
        version: str | None = None,  # noqa: ARG002
        **variables: str,
    ) -> str:
        if name not in self._cache:
            path = self._dir / f"{name}.yaml"
            if not path.exists():
                msg = f"Prompt file not found: {path}"
                raise KeyError(msg)

            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)

            self._cache[name] = data["template"]
            log.debug("yaml_prompt_repo.loaded", name=name, path=str(path))

        return self._cache[name].format_map(variables)
