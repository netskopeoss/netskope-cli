"""Netskope CLI exception hierarchy.

All CLI-specific exceptions inherit from NetskopeError and carry an exit code,
an optional human-friendly suggestion, and optional machine-readable details.
"""

from __future__ import annotations

from typing import Any


class NetskopeError(Exception):
    """Base exception for all Netskope CLI errors."""

    exit_code: int = 1

    def __init__(
        self,
        message: str,
        *,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.suggestion = suggestion
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        parts = [self.message]
        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")
        return "\n".join(parts)


class AuthError(NetskopeError):
    """Authentication failed (invalid or missing credentials)."""

    exit_code: int = 3

    def __init__(
        self,
        message: str = "Authentication failed.",
        *,
        suggestion: str | None = "Check your API token with `netskope config show`.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, details=details)


class AuthorizationError(NetskopeError):
    """Authenticated but not authorized for the requested resource."""

    exit_code: int = 4

    def __init__(
        self,
        message: str = "You are not authorized to perform this action.",
        *,
        suggestion: str | None = "Verify your account has the required permissions.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, details=details)


class NotFoundError(NetskopeError):
    """The requested resource was not found."""

    exit_code: int = 5

    def __init__(
        self,
        message: str = "Resource not found.",
        *,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, details=details)


class APIError(NetskopeError):
    """Generic API error for unexpected server responses."""

    exit_code: int = 1

    def __init__(
        self,
        message: str = "An API error occurred.",
        *,
        status_code: int | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, suggestion=suggestion, details=details)


class RateLimitError(NetskopeError):
    """API rate limit exceeded."""

    exit_code: int = 1

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please wait and try again.",
        *,
        retry_after: int | None = None,
        suggestion: str | None = "Wait a moment before retrying, or reduce request frequency.",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, suggestion=suggestion, details=details)


class ConfigError(NetskopeError):
    """Configuration is missing or invalid."""

    exit_code: int = 78

    def __init__(
        self,
        message: str = "Configuration error.",
        *,
        suggestion: str | None = "Run `netskope config setup` to configure the CLI.",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, details=details)


class ValidationError(NetskopeError):
    """Input validation failed."""

    exit_code: int = 2

    def __init__(
        self,
        message: str = "Validation error.",
        *,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, suggestion=suggestion, details=details)
