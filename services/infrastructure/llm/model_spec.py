"""Per-call model resolution and the bounded model cache.

``ModelSpec`` is everything that determines which chat model gets built — so it
is also the cache key. ``effective_spec`` overlays the caller's ``UserLLMConfig``
(contextvar) onto the adapter's env defaults; ``ModelCache`` builds lazily via
``build_chat_model`` (imported at call time so importing an adapter stays cheap).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

CHAT_LANES = frozenset({"base", "synthesis", "retrieval"})


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model_name: str
    temperature: float
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    reasoning: str | None = None
    num_ctx: int | None = None
    allow_cloud: bool = False


def effective_spec(defaults: ModelSpec, lane: str | None) -> ModelSpec:
    """The caller's UserLLMConfig (contextvar) → env ``defaults``, plus the lane's
    reasoning override. Cloud-without-key is raised by ``build_chat_model`` when
    the spec is built, not here.
    """
    from infrastructure.llm.llm_context import get_user_config
    from infrastructure.llm.reasoning_context import get_lane_override

    spec = defaults
    cfg = get_user_config()
    if cfg is not None:
        model = (cfg.chat_model or cfg.model) if lane in CHAT_LANES else cfg.model
        spec = replace(
            spec,
            provider=cfg.provider,
            model_name=model or defaults.model_name,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
        )
    return replace(spec, reasoning=get_lane_override(lane) or spec.reasoning)


class ModelCache:
    """Bounded per-adapter cache of built chat models keyed by ModelSpec.

    # ponytail: OrderedDict LRU of 8 per adapter; promote to a process-wide
    # cache if adapters multiply.
    """

    def __init__(self, maxsize: int = 8) -> None:
        self._models: OrderedDict[ModelSpec, BaseChatModel] = OrderedDict()
        self._maxsize = maxsize

    def get(self, spec: ModelSpec) -> BaseChatModel:
        from infrastructure.llm import model_builder

        model = self._models.get(spec)
        if model is None:
            model = model_builder.build_chat_model(**asdict(spec))
            self._models[spec] = model
            if len(self._models) > self._maxsize:
                self._models.popitem(last=False)
        else:
            self._models.move_to_end(spec)
        return model

    def __len__(self) -> int:
        return len(self._models)
