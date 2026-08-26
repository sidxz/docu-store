"""Domain exceptions for business rule violations."""


class DomainError(Exception):
    """Base exception for domain layer."""


class ValidationError(DomainError):
    """Raised when input validation fails."""


class AggregateNotFoundError(DomainError):
    """Raised when an aggregate is not found in the repository."""


class ConcurrencyError(DomainError):
    """Raised when a concurrency conflict occurs (optimistic locking)."""


class InfrastructureError(Exception):
    """Raised when infrastructure operations fail (DB, network, etc.).

    Note: This intentionally does NOT inherit from DomainError.
    Infrastructure failures are operational concerns, not domain violations.
    """


class LLMError(InfrastructureError):
    """Base for LLM-lane failures. ``retryable`` drives Temporal's retry decision."""

    retryable: bool = False


class LLMNotConfiguredError(LLMError):
    """No provider/key resolvable for this caller (user config → env → nothing). Fail closed."""


class LLMAuthError(LLMError):
    """The provider rejected our credentials or billing (HTTP 401/402/403)."""


class LLMRateLimitedError(LLMError):
    """The provider rate-limited the call (HTTP 429) — worth retrying."""

    retryable = True
