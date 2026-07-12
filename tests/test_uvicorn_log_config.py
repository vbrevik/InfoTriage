"""test_uvicorn_log_config.py — gap-closure regression tests for the JSON log config.

Phase 7 07-02 gap closure: ensure the uvicorn access-log config still satisfies
the load-bearing invariants after any future edit.

MUST be a unit test (NOT db_live) so it runs on every pytest invocation,
matching the always-on pattern of tests/test_dsn_safety.py.
"""

import json
from importlib import resources

import pytest

from contracts.uvicorn_log_config import LOGGING_CONFIG


def _load_json_ssot() -> dict:
    """Read the JSON file that's the SSOT for the LOGGING_CONFIG dict."""
    with resources.files("contracts").joinpath("uvicorn-log-config.json").open(
        encoding="utf-8"
    ) as f:
        return json.load(f)


def test_logging_config_is_a_dict():
    assert isinstance(
        LOGGING_CONFIG, dict
    ), "LOGGING_CONFIG must be a dict (uvicorn.run expects log_config=dict)."


def test_logging_config_disable_existing_loggers_is_false():
    """disable_existing_loggers=False protects the setup_logging() handlers.

    If True, uvicorn's dictConfig wipes the root-logger handlers that
    setup_logging() attaches at module import time. The file-rotating handler
    and stdout handler would be lost on every uvicorn.run().
    """
    assert LOGGING_CONFIG.get("disable_existing_loggers") is False, (
        "disable_existing_loggers must be False so setup_logging() handlers survive "
        "uvicorn's dictConfig."
    )


def test_logging_config_uses_json_formatter():
    assert "formatters" in LOGGING_CONFIG, "formatters key missing"
    formatter = LOGGING_CONFIG["formatters"].get("json")
    assert formatter is not None, "json formatter missing"
    # json_log_formatter uses a callable string reference ('()' key in dictConfig).
    assert (
        formatter.get("()") == "json_log_formatter.JSONFormatter"
    ), "json formatter must reference json_log_formatter.JSONFormatter."


def test_logging_config_routes_uvicorn_loggers_to_json():
    """All three uvicorn loggers must emit JSON to stdout."""
    loggers = LOGGING_CONFIG.get("loggers", {})
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        assert name in loggers, f"{name} logger missing from config"
    # uvicorn.access must use the json handler and NOT propagate (avoid double-logging
    # via the root logger's stdout handler).
    access = loggers["uvicorn.access"]
    assert "default" in access["handlers"], "uvicorn.access must use the json handler"
    assert (
        access.get("propagate") is False
    ), "uvicorn.access.propagate must be False to avoid duplicate emission via root."


def test_logging_config_matches_json_ssot():
    """LOGGING_CONFIG dict and uvicorn-log-config.json must agree byte-for-byte.

    The JSON is the SSOT for CLI-launched services; the dict is what callers
    pass to uvicorn.run(log_config=...). A drift between them is a footgun.
    """
    assert LOGGING_CONFIG == _load_json_ssot(), (
        "LOGGING_CONFIG dict does not match uvicorn-log-config.json "
        "\u2014 one of them was edited without the other."
    )


def test_uvicorn_log_config_json_is_shipped_as_package_data():
    """The JSON file must be installed alongside the Python package.

    Without package-data registration, importlib.resources won't find it in a
    wheel-installed contracts package \u2014 the dict would silently fall back to
    whatever is in the source tree.
    """
    with resources.files("contracts").joinpath("uvicorn-log-config.json").open(
        encoding="utf-8"
    ) as f:
        raw = json.load(f)
    assert isinstance(raw, dict)
    assert raw.get("version") == 1
