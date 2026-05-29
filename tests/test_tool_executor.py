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
