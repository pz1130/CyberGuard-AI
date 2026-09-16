""".env is shared with docker-compose, so the app must ignore what isn't its.

`cp .env.example .env` is the documented setup step, and it made `app.config`
raise on import with 12 `extra_forbidden` errors: POSTGRES_PORT, API_PORT,
RUNNER_TOKEN, SKILL_RUNNER_TOKEN and friends are read by docker-compose to wire
up *other* containers, and the API has no business having an opinion about them.

pydantic-settings only enforces `extra` against a dotenv file, not against real
environment variables — which is why the containers were healthy while a local
`pytest` could not import the app at all.
"""
from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent


def _load_settings_with(env_text: str, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(env_text)
    monkeypatch.chdir(tmp_path)
    from app.config import Settings
    return Settings(_env_file=str(env_file))


def test_the_documented_setup_step_produces_a_usable_config(tmp_path, monkeypatch):
    """cp .env.example .env — the first thing any new operator does."""
    example = (REPO / ".env.example").read_text()
    settings = _load_settings_with(example, tmp_path, monkeypatch)
    assert settings.ENVIRONMENT


def test_compose_only_variables_are_ignored_rather_than_rejected(tmp_path, monkeypatch):
    settings = _load_settings_with(
        "ENVIRONMENT=testing\n"
        "API_PORT=8000\n"
        "WEBUI_PORT=3000\n"
        "POSTGRES_PORT=5432\n"
        "REDIS_PORT=6379\n"
        "POSTGRES_PASSWORD=x\n"
        "RUNNER_TOKEN=x\n"
        "SKILL_RUNNER_TOKEN=x\n"
        "EGRESS_PROXY_TOKEN=x\n",
        tmp_path, monkeypatch)
    assert settings.ENVIRONMENT == "testing"


def test_values_the_app_does_own_are_still_read(tmp_path, monkeypatch):
    """Ignoring extras must not turn into ignoring everything."""
    settings = _load_settings_with(
        "ENVIRONMENT=testing\nAPI_PORT=9999\nACCESS_TOKEN_EXPIRE_MINUTES=77\n",
        tmp_path, monkeypatch)
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 77


def test_every_key_in_the_example_file_is_either_a_setting_or_infrastructure(tmp_path):
    """A key that is neither is a typo in the shipped example, which is the
    thing `extra=forbid` was presumably meant to catch — this keeps that check
    where it belongs, on the file we ship, rather than on every operator."""
    import re

    from app.config import Settings

    # Read by docker-compose to configure containers other than the API.
    INFRASTRUCTURE = {
        "POSTGRES_PASSWORD", "POSTGRES_PORT", "REDIS_PORT", "API_PORT",
        "WEBUI_PORT", "RUNNER_TOKEN", "SKILL_RUNNER_TOKEN", "EGRESS_PROXY_TOKEN",
        "CYBERGUARD_ENV_FILE",
    }
    # Read straight from os.environ by a service instead of via Settings —
    # see app/services/email_service.py::_cfg. Worth knowing, because a value
    # placed only in .env never reaches os.environ: pydantic-settings parses
    # that file without exporting it. These work in the containers, where
    # compose's env_file injects real environment variables.
    READ_FROM_ENVIRON = {
        "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL", "SMTP_USE_TLS", "SMTP_ADMIN_EMAIL",
    }
    declared = set(Settings.model_fields)
    keys = set(re.findall(r'^([A-Z][A-Z0-9_]*)=',
                          (REPO / ".env.example").read_text(), re.M))
    unexplained = keys - declared - INFRASTRUCTURE - READ_FROM_ENVIRON
    assert unexplained == set(), (
        "keys in .env.example that are neither an app setting, known "
        f"infrastructure, nor read from os.environ: {sorted(unexplained)}"
    )
