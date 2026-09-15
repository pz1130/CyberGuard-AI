"""Bundle materialization: path safety and the read-only/scratch split."""
from __future__ import annotations

import base64
import os
import tempfile

import pytest

from skill_runner.materialize import MaterializeError, materialize, safe_relative_path


def _f(path: str, body: bytes) -> dict:
    return {"path": path, "content_b64": base64.b64encode(body).decode()}


def test_rejects_absolute_and_traversal_paths():
    for bad in ("/etc/passwd", "../x", "a/../../b", "C:/x"):
        with pytest.raises(MaterializeError):
            safe_relative_path(bad)


def test_accepts_ordinary_nested_paths():
    assert safe_relative_path("scripts/triage.py") == "scripts/triage.py"
    assert safe_relative_path("./refs/a.md") == "refs/a.md"


def test_materialize_writes_the_bundle_and_makes_a_scratch_dir():
    with tempfile.TemporaryDirectory() as root:
        bundle, scratch = materialize(
            [_f("scripts/x.py", b"print(1)"), _f("refs/a.md", b"hi")], root
        )
        assert open(os.path.join(bundle, "scripts", "x.py"), "rb").read() == b"print(1)"
        assert open(os.path.join(bundle, "refs", "a.md"), "rb").read() == b"hi"
        assert os.path.isdir(scratch)
        assert os.access(scratch, os.W_OK)


def test_bundle_tree_is_not_writable():
    # A script must not be able to rewrite its own approved contents mid-run;
    # the executing code would then differ from the digest that authorized it.
    with tempfile.TemporaryDirectory() as root:
        bundle, _ = materialize([_f("scripts/x.py", b"print(1)")], root)
        assert not os.access(os.path.join(bundle, "scripts", "x.py"), os.W_OK)


def test_traversal_inside_the_payload_is_refused():
    with tempfile.TemporaryDirectory() as root:
        with pytest.raises(MaterializeError):
            materialize([_f("../escape.py", b"x")], root)


def test_unlock_for_removal_makes_the_read_only_tree_deletable():
    # Unlinking needs write permission on the *directory*, so the tree
    # materialize() leaves behind cannot be removed until this runs.
    import shutil

    from skill_runner.materialize import unlock_for_removal

    root = tempfile.mkdtemp()
    materialize([_f("scripts/x.py", b"print(1)")], root)
    with pytest.raises(OSError):
        shutil.rmtree(root)
    unlock_for_removal(root)
    shutil.rmtree(root)
    assert not os.path.exists(root)
