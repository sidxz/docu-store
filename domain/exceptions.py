"""Domain exceptions for business rule violations."""


class DomainError(Exception):
    """Base exception for domain layer."""


class ValidationError(DomainError):
    """Raised when input validation fails."""
