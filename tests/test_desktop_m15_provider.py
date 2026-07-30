"""M1.5 provider config + FileVault probe (unit)."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(root))
    monkeypatch.delenv("CYBERGUARD_LLM_MODE", raising=False)
    monkeypatch.delenv("CYBERGUARD_LLM_API_KEY", raising=False)
    import importlib
    import apps.desktop.sidecar.paths as paths
    import apps.desktop.sidecar.provider as provider

    importlib.reload(paths)
    importlib.reload(provider)
    return root


def test_default_is_mock(data_dir):
    from apps.desktop.sidecar.provider import load_provider_config

    cfg = load_provider_config()
    assert cfg.mode == "mock"
    assert cfg.is_live is False
    assert cfg.public_status()["mode"] == "mock"
    assert "api_key" not in cfg.public_status()


def test_env_live_requires_key(data_dir, monkeypatch):
    from apps.desktop.sidecar import provider as provider_mod

    monkeypatch.setenv("CYBERGUARD_LLM_MODE", "live")
    # no key → mock fallback
    cfg = provider_mod.load_provider_config()
    assert cfg.is_live is False


def test_file_config_live(data_dir, monkeypatch):
    from apps.desktop.sidecar.paths import data_root
    from apps.desktop.sidecar import provider as provider_mod
    import importlib

    importlib.reload(provider_mod)
    p = data_root() / "provider.json"
    p.write_text(
        json.dumps(
            {
                "mode": "live",
                "base_url": "https://example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-test",
            }
        ),
        encoding="utf-8",
    )
    cfg = provider_mod.load_provider_config()
    assert cfg.is_live is True
    assert cfg.model == "gpt-test"
    assert cfg.public_status()["has_api_key"] is True
    assert "sk-test" not in json.dumps(cfg.public_status())


@pytest.mark.asyncio
async def test_live_chat_strips_think_and_uses_tools(data_dir, monkeypatch):
    from apps.desktop.sidecar.provider import ProviderConfig, live_chat

    fake_msg = SimpleNamespace(
        content="<think>secret</think>hello",
        tool_calls=None,
    )
    fake_resp = SimpleNamespace(choices=[SimpleNamespace(message=fake_msg)])
    create = AsyncMock(return_value=fake_resp)

    class FakeCompletions:
        def __init__(self):
            self.create = create

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self, **kw):
            self.chat = FakeChat()

    with patch("openai.AsyncOpenAI", FakeClient):
        cfg = ProviderConfig(
            mode="live",
            api_key="sk",
            base_url="https://example.com/v1",
            model="m",
        )
        out = await live_chat(cfg, [{"role": "user", "content": "hi"}])
    assert out == "hello"
    assert "secret" not in out


def test_filevault_non_darwin(monkeypatch):
    from apps.desktop.sidecar import filevault as fv
    import platform

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    st = fv.filevault_status()
    assert st["supported"] is False
    assert st["warning"] is None


def test_filevault_off_warning(monkeypatch):
    from apps.desktop.sidecar import filevault as fv
    import platform
    import subprocess

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    class R:
        stdout = "FileVault is Off."
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    st = fv.filevault_status()
    assert st["enabled"] is False
    assert st["warning"] and "FileVault is OFF" in st["warning"]


def test_watchdog_kills_children_when_ppid_one(monkeypatch):
    """Unit: when getppid returns 1, registry kill_all is invoked."""
    import apps.desktop.sidecar.process_group as pg
    import time

    reg = pg.ProcessRegistry()
    killed = []
    exited = []

    def fake_kill(pid, sig):
        killed.append((pid, sig))

    monkeypatch.setattr(pg.os, "getppid", lambda: 1)
    monkeypatch.setattr(pg.os, "kill", fake_kill)
    monkeypatch.setattr(pg.os, "killpg", lambda *a, **k: None)
    monkeypatch.setattr(pg.os, "_exit", lambda code: exited.append(code))

    reg.register(99999, "fake")
    reg.start_watchdog(interval_sec=0.05, exit_on_orphan=True)
    deadline = time.time() + 2
    while time.time() < deadline and not killed:
        time.sleep(0.05)
    reg.stop_watchdog()
    if reg._watchdog:
        reg._watchdog.join(timeout=1)
    assert any(pid == 99999 for pid, _ in killed)
    assert exited  # would have os._exit'd
