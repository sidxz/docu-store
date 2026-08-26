from __future__ import annotations

import pytest

from domain.exceptions import LLMAuthError, LLMNotConfiguredError, LLMRateLimitedError
from infrastructure.llm.errors import classify, translate_provider_errors


class _SdkStatus(Exception):
    """openai / anthropic SDK shape: ``status_code``."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


class _GenAI(Exception):
    """google-genai APIError shape: ``code``."""

    def __init__(self, code: int) -> None:
        super().__init__(f"genai {code}")
        self.code = code


class _Langextract(Exception):
    """langextract InferenceRuntimeError shape: ``original``."""

    def __init__(self, original: BaseException) -> None:
        super().__init__("inference failed")
        self.original = original


@pytest.mark.parametrize("code", [401, 402, 403])
def test_auth_statuses_are_auth_errors(code: int) -> None:
    assert isinstance(classify(_SdkStatus(code)), LLMAuthError)
    assert isinstance(classify(_GenAI(code)), LLMAuthError)


def test_429_is_rate_limited_and_retryable() -> None:
    err = classify(_SdkStatus(429))
    assert isinstance(err, LLMRateLimitedError)
    assert err.retryable is True


@pytest.mark.parametrize(
    "exc", [_SdkStatus(500), _GenAI(503), RuntimeError("boom"), ConnectionError()]
)
def test_unknown_errors_are_not_classified(exc: BaseException) -> None:
    assert classify(exc) is None


def test_unwraps_langextract_original_and_cause() -> None:
    assert isinstance(classify(_Langextract(_SdkStatus(401))), LLMAuthError)
    try:
        raise RuntimeError("outer") from _GenAI(429)
    except RuntimeError as chained:
        assert isinstance(classify(chained), LLMRateLimitedError)


def test_existing_llm_error_is_returned_as_is() -> None:
    err = LLMNotConfiguredError("no key")
    assert classify(err) is err


def test_message_carries_status_not_secrets() -> None:
    err = classify(_SdkStatus(401))
    assert "HTTP 401" in str(err)
    assert "_SdkStatus" in str(err)
    assert "http 401" not in str(err)  # provider's own message text is not copied


def test_translate_reraises_typed_and_passes_unknown_through() -> None:
    with pytest.raises(LLMAuthError) as info, translate_provider_errors():
        raise _SdkStatus(403)
    assert isinstance(info.value.__cause__, _SdkStatus)

    with pytest.raises(RuntimeError), translate_provider_errors():
        raise RuntimeError("network")

    with pytest.raises(LLMNotConfiguredError), translate_provider_errors():
        raise LLMNotConfiguredError("x")
