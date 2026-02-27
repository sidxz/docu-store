from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class LangfusePromptRepository:
    """PromptRepositoryPort adapter that fetches and renders prompts from Langfuse.

    Uses the official Langfuse compile(**variables) API — no custom normalization.
    Langfuse handles {{variable}} substitution internally and validates that all
    required variables are provided.

    Set PROMPT_REPOSITORY_TYPE=langfuse (the default) to activate.

    Requires: LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY in env.
    """

    def __init__(
        self,
        host: str,
        public_key: str,
        secret_key: str,
    ) -> None:
        self._host = host
        self._public_key = public_key
        self._secret_key = secret_key
        self._client = None  # lazy-initialised

    def _get_client(self):  # noqa: ANN202
        if self._client is None:
            from langfuse import Langfuse  # noqa: PLC0415

            self._client = Langfuse(
                host=self._host,
                public_key=self._public_key,
                secret_key=self._secret_key,
            )
            log.info("langfuse_prompt_repo.connected", host=self._host)
        return self._client

    async def render_prompt(
        self,
        name: str,
        version: str | None = None,
        **variables: str,
    ) -> str:
        client = self._get_client()
        try:
            kwargs: dict = {"name": name, "label": "latest"}
            if version is not None:
                kwargs["version"] = int(version)
                del kwargs["label"]  # version takes precedence over label

            lf_prompt = client.get_prompt(**kwargs)
            rendered = lf_prompt.compile(**variables)

            log.debug(
                "langfuse_prompt_repo.rendered",
                name=name,
                version=lf_prompt.version,
            )
            return rendered
        except Exception as exc:
            msg = f"Failed to render prompt '{name}' from Langfuse: {exc}"
            raise RuntimeError(msg) from exc
