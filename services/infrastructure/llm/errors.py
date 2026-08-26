"""Map provider SDK exceptions onto the LLMError taxonomy.

openai / anthropic SDK errors carry ``status_code``; google-genai's ``APIError``
carries ``code``; langextract wraps the SDK error as
``InferenceRuntimeError(original=...)``. Anything unrecognised passes through
untouched (network errors → Temporal's default retry).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from domain.exceptions import LLMAuthError, LLMError, LLMRateLimitedError

_AUTH_STATUSES = frozenset({401, 402, 403})
_MAX_DEPTH = 5


def _status(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        code = getattr(exc, attr, None)
        if isinstance(code, int) and not isinstance(code, bool):
            return code
    return None


def classify(exc: BaseException) -> LLMError | None:
    """The typed error for ``exc`` (or one wrapped inside it), or None."""
    cur: BaseException | None = exc
    for _ in range(_MAX_DEPTH):
        if cur is None:
            return None
        if isinstance(cur, LLMError):
            return cur
        code = _status(cur)
        if code in _AUTH_STATUSES:
            return LLMAuthError(f"LLM provider rejected the request (HTTP {code}): {cur}")
        if code == 429:
            return LLMRateLimitedError(f"LLM provider rate-limited the request: {cur}")
        cur = getattr(cur, "original", None) or cur.__cause__
    return None


@contextmanager
def translate_provider_errors() -> Iterator[None]:
    """Re-raise provider SDK failures as LLMError subclasses; pass everything else through."""
    try:
        yield
    except LLMError:
        raise
    except Exception as exc:
        typed = classify(exc)
        if typed is None:
            raise
        raise typed from exc
