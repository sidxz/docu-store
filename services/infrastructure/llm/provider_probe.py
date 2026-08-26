"""Live check of a UserLLMConfig: one tiny completion per distinct lane model.

Details are key-free by construction: ``LLMError`` messages come from
``infrastructure.llm.errors`` (no payload echo) and anything else is reported
by exception type only — SDK errors can embed request headers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from domain.exceptions import LLMError
from infrastructure.llm.errors import translate_provider_errors
from infrastructure.llm.model_builder import build_chat_model

if TYPE_CHECKING:
    from application.ports.user_llm_config import UserLLMConfig

LaneResult = tuple[bool, str | None]


async def probe_user_llm_config(cfg: UserLLMConfig, *, allow_cloud: bool) -> dict[str, LaneResult]:
    """``{"batch": (ok, detail), "chat": (ok, detail)}`` — same model probed once."""
    lanes = {"batch": cfg.model, "chat": cfg.chat_model or cfg.model}
    by_model: dict[str | None, LaneResult] = {}
    for model in lanes.values():
        if model not in by_model:
            by_model[model] = await _probe_model(cfg, model, allow_cloud=allow_cloud)
    return {lane: by_model[model] for lane, model in lanes.items()}


async def _probe_model(cfg: UserLLMConfig, model: str | None, *, allow_cloud: bool) -> LaneResult:
    if not model:
        return False, "No model configured."
    try:
        with translate_provider_errors():
            llm = build_chat_model(
                provider=cfg.provider,
                model_name=model,
                temperature=0.0,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                allow_cloud=allow_cloud,
            )
            await llm.ainvoke([HumanMessage(content="Reply with OK.")])
    except LLMError as exc:
        return False, str(exc)
    except Exception as exc:  # never echo SDK payloads
        return False, f"Unexpected {type(exc).__name__}"
    return True, None
