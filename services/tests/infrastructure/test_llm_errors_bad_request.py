"""classify(): provider 4xx other than auth/rate-limit is a non-retryable LLMBadRequestError."""

from __future__ import annotations

from domain.exceptions import LLMAuthError, LLMBadRequestError, LLMRateLimitedError
from infrastructure.llm.errors import classify


class _OpenAIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Error code: {status_code} - {{'error': {{'message': {message!r}}}}}")
        self.status_code = status_code
        self.body = {"error": {"message": message}}


def test_400_is_bad_request_non_retryable_with_provider_detail() -> None:
    err = classify(_OpenAIError(400, "Function tools with reasoning_effort are not supported"))
    assert isinstance(err, LLMBadRequestError)
    assert err.retryable is False
    assert "HTTP 400" in str(err) and "Function tools with reasoning_effort" in str(err)


def test_404_and_422_are_bad_requests() -> None:
    assert isinstance(classify(_OpenAIError(404, "model not found")), LLMBadRequestError)
    assert isinstance(classify(_OpenAIError(422, "unprocessable")), LLMBadRequestError)


def test_auth_and_rate_limit_keep_their_types_and_stay_key_free() -> None:
    auth = classify(_OpenAIError(401, "Incorrect API key provided: sk-abc***xyz"))
    assert isinstance(auth, LLMAuthError) and "sk-abc" not in str(auth)
    assert isinstance(classify(_OpenAIError(429, "slow down")), LLMRateLimitedError)


def test_5xx_stays_generic() -> None:
    assert classify(_OpenAIError(502, "bad gateway")) is None


def test_provider_detail_is_truncated() -> None:
    err = classify(_OpenAIError(400, "x" * 1000))
    assert len(str(err)) < 450
