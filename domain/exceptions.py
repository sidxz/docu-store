"""Domain exceptions for business rule violations."""


class DomainError(Exception):
    """Base exception for domain layer."""


class ValidationError(DomainError):
    """Raised when input validation fails."""


class AggregateNotFoundError(DomainError):
    """Raised when an aggregate is not found in the repository."""


class ConcurrencyError(DomainError):
    """Raised when a concurrency conflict occurs (optimistic locking)."""


class InfrastructureError(DomainError):
    """Raised when infrastructure operations fail (DB, network, etc.)."""
