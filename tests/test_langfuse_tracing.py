"""Tests for the optional Langfuse tracing layer (app/core/langfuse_tracing.py).

The Langfuse SDK is never imported here — tests inject a fake client via the
module-level `_client`, so they run with or without the package installed.
"""
from unittest.mock import MagicMock

import app.core.langfuse_tracing as lf


def test_record_generation_is_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(lf, "_client", None)
    # Must not raise even with no client and no active trace.
    lf.record_generation(name="chat", model="gpt-4o",
                         input=[{"role": "user", "content": "hi"}], output="hello")


def test_trace_run_sets_and_resets_contextvar(monkeypatch):
    monkeypatch.setattr(lf, "_client", None)
    assert lf._ctx.get() is None
    with lf.trace_run(session_id="s1", agent_name="osint", user_id=7):
        ctx = lf._ctx.get()
        assert ctx.session_id == "s1" and ctx.agent_name == "osint" and ctx.user_id == 7
    assert lf._ctx.get() is None                      # reset on exit


def test_record_generation_emits_under_session_trace(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(lf, "_client", client)

    with lf.trace_run(session_id="conv-1", agent_name="osint", user_id=7):
        lf.record_generation(
            name="chat", model="m",
            input=[{"role": "user", "content": "hi"}], output="hello",
            usage=MagicMock(prompt_tokens=3, completion_tokens=2, total_tokens=5))

    # A trace was opened carrying the session, and a generation nested under it.
    client.trace.assert_called_once()
    assert client.trace.call_args.kwargs["session_id"] == "conv-1"
    trace = client.trace.return_value
    trace.generation.assert_called_once()
    g = trace.generation.call_args.kwargs
    assert g["name"] == "chat" and g["model"] == "m" and g["output"] == "hello"
    assert g["usage"] == {"input": 3, "output": 2, "total": 5}


def test_record_generation_swallows_sdk_errors(monkeypatch):
    client = MagicMock()
    client.trace.return_value.generation.side_effect = RuntimeError("sdk boom")
    monkeypatch.setattr(lf, "_client", client)
    # Tracing must never break the caller.
    with lf.trace_run(session_id="c", agent_name="a"):
        lf.record_generation(name="chat", model="m", input=[], output="x")
