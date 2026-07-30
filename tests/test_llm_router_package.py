"""M0a-1: packages/llm_router boundary and pure helpers (behavior-preserving)."""
import ast
from pathlib import Path

import pytest

from llm_router import acall_with_retry, extract_json_object, model_name, rate_limit, strip_think_blocks
from llm_router.utils import extract_json_object as ej
from llm_router.utils import model_name as mn
from llm_router.utils import strip_think_blocks as stb


# ---------------------------------------------------------------------------
# Package boundary: no agent / app imports inside llm_router
# ---------------------------------------------------------------------------

_PKG = Path(__file__).resolve().parents[1] / "packages" / "llm_router"
_FORBIDDEN_ROOTS = ("app", "sqlalchemy", "redis", "celery", "fastapi", "langgraph")


def _iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if p.name == "py.typed":
            continue
        yield p


def test_llm_router_package_has_no_forbidden_imports():
    """packages/llm_router must not pull agent stack or app.* (INV-style boundary)."""
    offenders = []
    for path in _iter_py_files(_PKG):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _FORBIDDEN_ROOTS:
                        offenders.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in _FORBIDDEN_ROOTS:
                    offenders.append(f"{path.name}: from {node.module}")
    assert not offenders, "forbidden imports in llm_router:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# Pure utils — same behavior as former private methods on LLMRouter
# ---------------------------------------------------------------------------

def test_model_name_str_and_dict():
    assert mn("gpt-4o") == "gpt-4o"
    assert mn({"name": "gpt-4o", "model_type": "chat"}) == "gpt-4o"
    assert mn(None) is None


def test_strip_think_blocks():
    raw = "hello <think>secret</think> world"
    assert "secret" not in stb(raw)
    assert "hello" in stb(raw) and "world" in stb(raw)
    assert stb("<reasoning>x</reasoning>ok") == "ok"


def test_extract_json_object_with_think_prefix():
    text = '<think>planning</think>\n{"intent": "task_execution", "n": 1}'
    data = ej(text)
    assert data == {"intent": "task_execution", "n": 1}


def test_extract_json_object_pure_json():
    assert ej('{"a": 1}') == {"a": 1}
    assert ej("not json") is None


def test_public_exports_match_utils():
    assert model_name is mn
    assert strip_think_blocks is stb
    assert extract_json_object is ej
    assert callable(acall_with_retry) and callable(rate_limit)


def test_app_core_resilience_reexports_package():
    """Old import path still works and points at package implementation."""
    from app.core import llm_resilience as legacy
    from llm_router import resilience as pkg

    assert legacy.acall_with_retry is pkg.acall_with_retry
    assert legacy.rate_limit is pkg.rate_limit
