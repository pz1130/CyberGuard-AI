"""`generate_summary` asks for a JSON object and falls back to plain text.

The fallback must only trigger when the provider rejects the *request shape*.
Catching everything turned a rate-limit or a dropped connection into a second
full-context request — paying twice for the failure.
"""
import pytest

from app.services.llm_router import is_response_format_rejection


class _ApiError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def test_unsupported_response_format_is_a_rejection():
    err = _ApiError(
        "Invalid parameter: 'response_format' of type 'json_object' is not supported",
        status_code=400)
    assert is_response_format_rejection(err) is True


def test_unknown_json_object_value_is_a_rejection():
    assert is_response_format_rejection(
        _ApiError("unknown value json_object", status_code=422)) is True


def test_rate_limit_is_not_a_rejection():
    assert is_response_format_rejection(
        _ApiError("Rate limit exceeded", status_code=429)) is False


def test_transport_failure_is_not_a_rejection():
    assert is_response_format_rejection(
        ConnectionError("connection reset by peer")) is False


def test_server_error_is_not_a_rejection():
    assert is_response_format_rejection(
        _ApiError("internal server error", status_code=500)) is False
