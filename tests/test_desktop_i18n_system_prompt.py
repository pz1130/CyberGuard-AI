"""i18n: language directive must append to default_prompt, not replace it."""
from __future__ import annotations

import importlib

import pytest

from apps.desktop.sidecar.mock_agent import MockAgentHost


LANGUAGE_DIRECTIVE = (
    "Respond in English. Keep tool names, file paths, hashes and identifiers verbatim."
)


@pytest.mark.asyncio
async def test_system_prompt_appends_not_replaces_default_prompt(tmp_path, monkeypatch):
    """English UI passes languageDirective via system_prompt; auth bounds / INV-39 stay."""
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.mcp_config as mcp_config

    importlib.reload(paths)
    importlib.reload(mcp_config)

    import apps.desktop.sidecar.mock_agent as ma

    captured: dict = {}

    async def fake_run_loop(*, system_prompt, **_kwargs):
        captured["prompt"] = system_prompt
        yield {
            "type": "answer_ready",
            "candidate_text": "ok",
            "status": "completed",
        }

    monkeypatch.setattr(ma, "run_loop", fake_run_loop)

    host = MockAgentHost()
    async for _ in host.run(
        task="hello",
        tier="readonly",
        system_prompt=LANGUAGE_DIRECTIVE,
    ):
        pass

    prompt = captured.get("prompt") or ""
    assert "source_trust=hostile" in prompt
    assert "Current authorization bounds" in prompt
    assert LANGUAGE_DIRECTIVE in prompt
    # Must not be replace-only: directive alone would wipe identity/bounds
    assert prompt.strip() != LANGUAGE_DIRECTIVE
    assert prompt.index("Current authorization bounds") < prompt.index(
        LANGUAGE_DIRECTIVE
    )
