"""Desktop agent emits token stream events for UI live output."""
from __future__ import annotations

import pytest

from apps.desktop.sidecar.mock_agent import MockAgentHost


@pytest.mark.asyncio
async def test_mock_agent_streams_tokens_on_final_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path / "cg"))
    monkeypatch.setenv("CYBERGUARD_LLM_MODE", "mock")
    monkeypatch.delenv("CYBERGUARD_LLM_API_KEY", raising=False)
    monkeypatch.setenv("CYBERGUARD_SECRETS_BACKEND", "file")
    monkeypatch.setenv("CYBERGUARD_PLAN_AUTO_APPROVE", "1")
    from apps.desktop.sidecar.plan_mode import reset_plan_store_for_tests

    reset_plan_store_for_tests()

    host = MockAgentHost()
    types = []
    deltas = []
    async for ev in host.run(
        task="简单说明系统状态",
        tier="readonly",
    ):
        types.append(ev.get("type"))
        if ev.get("type") == "token":
            deltas.append(str(ev.get("delta") or ""))

    assert "answer_ready" in types
    # Mock final answers are chunk-streamed via token events
    assert len(deltas) >= 1, f"expected token deltas, types={types}"
    assert "token_done" in types
    joined = "".join(deltas)
    assert len(joined) > 0
