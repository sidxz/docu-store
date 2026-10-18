"""Request-scoped answer-formatting switch (set by the chat use case from the
workspace's setting, read by the chat agents). Same bridge as ``stats_context``:
the agents are singletons and the router does not forward per-turn arguments.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_answer_formatting: ContextVar[bool | None] = ContextVar("answer_formatting", default=None)


def set_answer_formatting(on: bool | None) -> Token:
    return _answer_formatting.set(on)


def reset_answer_formatting(token: Token) -> None:
    _answer_formatting.reset(token)


def answer_formatting_enabled() -> bool:
    """The workspace's choice for this turn, else ``CHAT_ENABLE_ANSWER_FORMATTING``."""
    from infrastructure.config import settings

    on = _answer_formatting.get()
    return settings.chat_enable_answer_formatting if on is None else on
