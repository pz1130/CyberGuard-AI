import json
import pytest
from app.services.tool_executor import build_argv, ToolArgError


SCHEMA = {"type": "object",
          "properties": {"ports": {"type": "string"}, "target": {"type": "string"}},
          "required": ["target"]}


def test_build_argv_fills_placeholders_as_single_tokens():
    argv = build_argv("nmap -sV -p {ports} {target}", SCHEMA,
                      {"ports": "80,443", "target": "example.com"})
    assert argv == ["nmap", "-sV", "-p", "80,443", "example.com"]


def test_build_argv_arg_with_spaces_stays_one_token():
    argv = build_argv("echo {msg}", {"type": "object",
                      "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
                      {"msg": "hello world; rm -rf /"})
    assert argv == ["echo", "hello world; rm -rf /"]


def test_build_argv_rejects_unknown_key():
    with pytest.raises(ToolArgError):
        build_argv("echo {msg}", {"type": "object",
                   "properties": {"msg": {}}, "required": []}, {"bogus": "x"})


def test_build_argv_rejects_missing_required():
    with pytest.raises(ToolArgError):
        build_argv("nmap {target}", SCHEMA, {"ports": "80"})


def test_build_argv_rejects_unfilled_placeholder():
    with pytest.raises(ToolArgError):
        build_argv("nmap {target} {ports}", SCHEMA, {"target": "x"})


def test_build_argv_rejects_embedded_placeholder():
    with pytest.raises(ToolArgError):
        build_argv("nmap -p{ports}", SCHEMA, {"ports": "80", "target": "x"})


from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def _tool(**kw):
    base = dict(command_template="echo {msg}",
                input_schema_json=json.dumps({"type": "object",
                    "properties": {"msg": {"type": "string"}}, "required": ["msg"]}),
                timeout_seconds=30, permission_level="medium", required_permission=None)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_execute_tool_dispatches_to_runner():
    from app.services import tool_executor as te
    fake_resp = SimpleNamespace(status_code=200, json=lambda: {
        "stdout": "hi", "stderr": "", "exit_code": 0, "duration_ms": 5, "timed_out": False})
    client = AsyncMock()
    client.__aenter__.return_value.post = AsyncMock(return_value=fake_resp)
    with patch.object(te.httpx, "AsyncClient", return_value=client):
        res = await te.execute_tool(_tool(), {"msg": "hi"}, user_id=1)
    assert res["status"] == "completed"
    assert res["stdout"] == "hi"


@pytest.mark.asyncio
async def test_execute_tool_high_permission_needs_approval():
    from app.services import tool_executor as te
    with patch.object(te, "_create_approval", AsyncMock()):
        res = await te.execute_tool(_tool(permission_level="high"), {"msg": "x"}, user_id=1)
    assert res["status"] == "needs_approval"


@pytest.mark.asyncio
async def test_execute_tool_rejects_bad_args():
    from app.services import tool_executor as te
    res = await te.execute_tool(_tool(), {"bogus": "x"}, user_id=1)
    assert res["status"] == "error"
    assert "unknown argument" in res["error"]


@pytest.mark.asyncio
async def test_execute_tool_rbac_denied():
    from app.services import tool_executor as te
    res = await te.execute_tool(_tool(required_permission="tool:exec"),
                                {"msg": "x"}, user_id=1, caller_permissions=set())
    assert res["status"] == "error"
    assert "permission" in res["error"].lower()


def test_build_argv_rejects_non_enum_value():
    schema = {"type": "object", "properties": {"mode": {"enum": ["a", "b"]}}, "required": []}
    with pytest.raises(ToolArgError):
        build_argv("run {mode}", schema, {"mode": "c"})


def test_build_argv_rejects_non_integer():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": []}
    with pytest.raises(ToolArgError):
        build_argv("run {n}", schema, {"n": "abc"})


def test_build_argv_accepts_valid_integer_string():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": []}
    assert build_argv("run {n}", schema, {"n": "42"}) == ["run", "42"]
