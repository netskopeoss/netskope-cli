"""Tests for netskope_cli.core.exceptions."""

from __future__ import annotations

import pytest

from netskope_cli.core.exceptions import (
    APIError,
    AuthError,
    AuthorizationError,
    ConfigError,
    NetskopeError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestExitCodes:
    @pytest.mark.parametrize(
        "exc_cls, expected_code",
        [
            (NetskopeError, 1),
            (AuthError, 3),
            (AuthorizationError, 4),
            (NotFoundError, 5),
            (APIError, 1),
            (RateLimitError, 1),
            (ConfigError, 78),
            (ValidationError, 2),
        ],
    )
    def test_exit_code(self, exc_cls: type[NetskopeError], expected_code: int) -> None:
        exc = exc_cls("boom")
        assert exc.exit_code == expected_code


# ---------------------------------------------------------------------------
# String representation
# ---------------------------------------------------------------------------


class TestStrRepresentation:
    def test_message_only(self) -> None:
        exc = NetskopeError("Something failed")
        assert str(exc) == "Something failed"

    def test_message_with_suggestion(self) -> None:
        exc = NetskopeError("Something failed", suggestion="Try again")
        result = str(exc)
        assert "Something failed" in result
        assert "Suggestion: Try again" in result

    def test_default_suggestion_auth_error(self) -> None:
        exc = AuthError()
        assert "Suggestion:" in str(exc)
        assert "API token" in str(exc)

    def test_default_suggestion_config_error(self) -> None:
        exc = ConfigError()
        assert "config setup" in str(exc)

    def test_no_suggestion_shows_message_only(self) -> None:
        exc = NotFoundError("missing", suggestion=None)
        assert str(exc) == "missing"


# ---------------------------------------------------------------------------
# Details dict
# ---------------------------------------------------------------------------


class TestDetails:
    def test_details_preserved(self) -> None:
        details = {"resource_id": "abc", "type": "policy"}
        exc = NetskopeError("failed", details=details)
        assert exc.details == details

    def test_details_default_empty_dict(self) -> None:
        exc = NetskopeError("failed")
        assert exc.details == {}

    def test_details_none_becomes_empty_dict(self) -> None:
        exc = NetskopeError("failed", details=None)
        assert exc.details == {}


# ---------------------------------------------------------------------------
# Special attributes
# ---------------------------------------------------------------------------


class TestSpecialAttributes:
    def test_api_error_status_code(self) -> None:
        exc = APIError("oops", status_code=500)
        assert exc.status_code == 500

    def test_api_error_status_code_default_none(self) -> None:
        exc = APIError("oops")
        assert exc.status_code is None

    def test_rate_limit_retry_after(self) -> None:
        exc = RateLimitError("slow down", retry_after=30)
        assert exc.retry_after == 30

    def test_rate_limit_retry_after_default_none(self) -> None:
        exc = RateLimitError()
        assert exc.retry_after is None


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


class TestInheritance:
    @pytest.mark.parametrize(
        "exc_cls",
        [AuthError, AuthorizationError, NotFoundError, APIError, RateLimitError, ConfigError, ValidationError],
    )
    def test_all_subclass_netskope_error(self, exc_cls: type[NetskopeError]) -> None:
        assert issubclass(exc_cls, NetskopeError)

    def test_netskope_error_is_exception(self) -> None:
        assert issubclass(NetskopeError, Exception)

    def test_catchable_as_base(self) -> None:
        with pytest.raises(NetskopeError):
            raise AuthError("fail")
