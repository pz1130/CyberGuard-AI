# Executable Skill Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a reviewed script inside a skill bundle execute as a normal, fully-gated `Tool`, in a dedicated network-isolated sandbox container.

**Architecture:** An admin promotes one bundle script into a `Tool` row carrying the bundle's sha256 digest. Execution takes the existing `run_tool_call` path unchanged — same kill switch, RBAC, gatekeeper, approval, safety envelope, audit — and only `_pool_execute` branches, posting the bundle to a second runner (`skill-runner`) that materializes it into tmpfs, runs it with a minimal environment holding no secrets, and deletes it.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, pytest, Docker Compose, React/TypeScript (webui).

**Spec:** `docs/superpowers/specs/2026-09-15-skill-script-execution-design.md`

## Global Constraints

- Scripts run with **`python3` or `sh` only, Python standard library only**. No third-party packages in the skill-runner image beyond what the runner service itself needs.
- Interpreter flags are **forbidden**: built argv is exactly `[interpreter, source_script_path, *arguments]`.
- `MINIMAL_ENV` for script subprocesses contains **only** `PATH`, `LANG`, `PYTHONDONTWRITEBYTECODE`, `HOME`, `TMPDIR`. **No token, no secret, ever.**
- Phase 1 accepts `script_network == "none"` only. `"allowlist"` must be **rejected** by the promotion endpoint.
- `skill_runner/` is a standalone package. It must **not** import from `app`, `agent_core`, or `tool_runner` — same rule `tool_runner/` already follows.
- Bundle path safety everywhere: reject absolute paths, `..` components, and symlink entries.
- Existing `build_argv()` in `app/services/tool_executor.py` is **reused unmodified**. Do not write a second argv builder.
- New migration revision id: `038_skill_script_tools`, `down_revision = "037_skill_bundle_files"`.
- Run the suite with `make test` (spins up disposable Postgres/Redis). Single files: `make test-env-up` then `DATABASE_URL=postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test REDIS_URL=redis://:cyberguard-test-only@localhost:56379/0 REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(python3 -c "print('0'*64)") SECRET_KEY=$(python3 -c "print('1'*64)") ENVIRONMENT=testing AUTO_APPROVE=false .venv/bin/python -m pytest <file> -v`.

---

## File Structure

| File | Responsibility |
|---|---|
| `tool_runner/main.py` (modify) | Task 1 only: stop leaking the runner env into tool subprocesses |
| `app/services/skill_bundle.py` (create) | Bundle digest + bundle loading. One source of truth used by promotion, invalidation, and execution |
| `app/models/skill.py` (modify) | 5 new `Tool` columns |
| `alembic/versions/038_skill_script_tools.py` (create) | The migration |
| `app/core/rbac.py` (modify) | `SKILL_SCRIPT_APPROVE` permission |
| `skill_runner/__init__.py`, `skill_runner/materialize.py`, `skill_runner/main.py` (create) | The sandbox service: path-safe materialization, minimal env, scratch dir, cleanup |
| `skill-runner/Dockerfile`, `skill-runner/requirements.lock` (create) | Its image |
| `docker-compose.yml` (modify) | Network split + the new service |
| `app/schemas/skill.py` (modify) | Promotion request/response schemas |
| `app/routers/skills.py` (modify) | Promotion endpoint + re-import invalidation |
| `app/services/tool_executor.py` (modify) | The one routing branch + digest re-verification |
| `webui/src/pages/Skills.tsx` (modify) | Promotion UI |

---

### Task 1: Stop the runner leaking its token into tool subprocesses

Independent of everything else and correct today. Lands first so it is reviewable on its own.

**Files:**
- Modify: `tool_runner/main.py:36`
- Test: `tests/test_tool_runner_endpoints.py`

**Interfaces:**
- Consumes: nothing
- Produces: `tool_runner.main.MINIMAL_ENV: dict[str, str]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tool_runner_endpoints.py`:

```python
class TestToolRunnerSubprocessEnv(unittest.TestCase):
    """A tool subprocess must not inherit the runner's own secrets.

    Without an explicit env=, create_subprocess_exec hands the child the whole
    parent environment — RUNNER_TOKEN included. That token buys arbitrary argv
    on this runner, so a child that can read it can bypass every gate in the API.
    """

    def setUp(self):
        self._ctx = TestClient(app)
        self.client = self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_child_cannot_see_runner_token(self):
        r = self.client.post(
            "/run",
            json={"argv": ["python3", "-c",
                           "import os; print(os.environ.get('RUNNER_TOKEN', '<absent>'))"],
                  "timeout": 20},
            headers=_HDR,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["stdout"].strip(), "<absent>")

    def test_child_still_gets_a_usable_path(self):
        r = self.client.post(
            "/run",
            json={"argv": ["python3", "-c", "import os; print(bool(os.environ.get('PATH')))"],
                  "timeout": 20},
            headers=_HDR,
        )
        self.assertEqual(r.json()["stdout"].strip(), "True")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_tool_runner_endpoints.py::TestToolRunnerSubprocessEnv -v`
Expected: `test_child_cannot_see_runner_token` FAILS — stdout is the token, not `<absent>`.

- [ ] **Step 3: Write minimal implementation**

In `tool_runner/main.py`, after `OUTPUT_MAX_BYTES`:

```python
# Explicit child environment. Without env=, create_subprocess_exec hands the
# child our whole environment, RUNNER_TOKEN included — and that token buys
# arbitrary argv on this service.
MINIMAL_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "LANG": os.environ.get("LANG", "C.UTF-8"),
    "PYTHONDONTWRITEBYTECODE": "1",
    "HOME": "/tmp",
}
```

Then in `run()`, change the subprocess call to:

```python
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=MINIMAL_ENV, start_new_session=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tool_runner_endpoints.py tests/test_tool_runner_mcp_host.py tests/test_tool_executor.py -v`
Expected: PASS. (MCP host has its own env plumbing and is untouched.)

- [ ] **Step 5: Commit**

```bash
git add tool_runner/main.py tests/test_tool_runner_endpoints.py
git commit -m "fix: stop tool subprocesses inheriting the runner token

create_subprocess_exec was called without env=, so every tool child got
the runner's whole environment including RUNNER_TOKEN. That token buys
arbitrary argv on the runner, so any child able to read it could bypass
the kill switch, RBAC, gatekeeper, approval and audit chain."
```

---

### Task 2: Bundle digest

**Files:**
- Create: `app/services/skill_bundle.py`
- Test: `tests/test_skill_bundle.py`

**Interfaces:**
- Consumes: `app.models.skill.SkillFile` (columns `path`, `content_text`, `content_blob`, `size_bytes`, `mime`)
- Produces:
  - `bundle_digest(files: Sequence[tuple[str, bytes]]) -> str` — 64-char lowercase hex
  - `file_bytes(row) -> bytes` — content of a `SkillFile` row as bytes
  - `async load_bundle(db, skill_id: int) -> list[tuple[str, bytes]]` — sorted by path
  - `async bundle_digest_for_skill(db, skill_id: int) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_bundle.py`:

```python
"""Bundle digest — what makes an approval bind to specific code."""
from __future__ import annotations

import pytest

from app.services.skill_bundle import bundle_digest, file_bytes


def test_digest_is_stable_and_order_independent():
    a = bundle_digest([("b.txt", b"two"), ("a.txt", b"one")])
    b = bundle_digest([("a.txt", b"one"), ("b.txt", b"two")])
    assert a == b
    assert len(a) == 64 and a == a.lower()


def test_digest_changes_when_any_content_changes():
    before = bundle_digest([("scripts/x.py", b"print(1)")])
    after = bundle_digest([("scripts/x.py", b"print(2)")])
    assert before != after


def test_digest_covers_siblings_not_just_the_entrypoint():
    # A python entrypoint can import a sibling; hashing only the entrypoint
    # would leave the real payload unprotected.
    before = bundle_digest([("scripts/x.py", b"import helper"), ("scripts/helper.py", b"ok")])
    after = bundle_digest([("scripts/x.py", b"import helper"), ("scripts/helper.py", b"evil")])
    assert before != after


def test_digest_changes_when_a_file_is_added_or_removed():
    one = bundle_digest([("a", b"x")])
    two = bundle_digest([("a", b"x"), ("b", b"")])
    assert one != two


def test_length_prefixing_prevents_boundary_collisions():
    # Without length prefixes, "ab" + "c" and "a" + "bc" would hash alike.
    left = bundle_digest([("ab", b"c")])
    right = bundle_digest([("a", b"bc")])
    assert left != right


def test_file_bytes_reads_text_and_blob_rows():
    class Row:
        def __init__(self, text, blob):
            self.content_text, self.content_blob = text, blob

    assert file_bytes(Row("hello", None)) == b"hello"
    assert file_bytes(Row(None, b"\x00\x01")) == b"\x00\x01"
    assert file_bytes(Row(None, None)) == b""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_bundle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.skill_bundle'`

- [ ] **Step 3: Write minimal implementation**

Create `app/services/skill_bundle.py`:

```python
"""Skill bundle digest and loading.

The digest is what makes approval bind to specific code: a Tool promoted from
a bundle stores the digest of that bundle, so a later re-import with different
script contents cannot reuse the old approval.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any, List, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def file_bytes(row: Any) -> bytes:
    """Content of a SkillFile row, whichever column it landed in."""
    if row.content_text is not None:
        return row.content_text.encode("utf-8")
    return row.content_blob or b""


def bundle_digest(files: Sequence[Tuple[str, bytes]]) -> str:
    """sha256 over the whole bundle, sorted by path.

    Each path and each body is length-prefixed so that moving the boundary
    between them cannot produce the same digest for a different bundle.
    """
    h = hashlib.sha256()
    for path, content in sorted(files, key=lambda f: f[0]):
        raw_path = path.encode("utf-8")
        h.update(struct.pack(">I", len(raw_path)))
        h.update(raw_path)
        h.update(struct.pack(">Q", len(content)))
        h.update(content)
    return h.hexdigest()


async def load_bundle(db: AsyncSession, skill_id: int) -> List[Tuple[str, bytes]]:
    """Every bundled file of a skill as (path, bytes), sorted by path."""
    from app.models.skill import SkillFile

    rows = (
        await db.execute(
            select(SkillFile).where(SkillFile.skill_id == skill_id).order_by(SkillFile.path)
        )
    ).scalars().all()
    return [(r.path, file_bytes(r)) for r in rows]


async def bundle_digest_for_skill(db: AsyncSession, skill_id: int) -> str:
    return bundle_digest(await load_bundle(db, skill_id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_skill_bundle.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/skill_bundle.py tests/test_skill_bundle.py
git commit -m "feat: add skill bundle digest"
```

---

### Task 3: Tool columns and migration

**Files:**
- Modify: `app/models/skill.py` (class `Tool`)
- Create: `alembic/versions/038_skill_script_tools.py`
- Test: `tests/test_skill_script_columns.py`

**Interfaces:**
- Consumes: Task 2 is unrelated here
- Produces: `Tool.source_skill_id`, `Tool.source_script_path`, `Tool.source_bundle_digest`, `Tool.script_network`, `Tool.script_network_allowlist`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_script_columns.py`:

```python
"""Tool gains the columns that mark it as a promoted skill script."""
from __future__ import annotations

from app.models.skill import Tool


def test_tool_has_skill_script_columns():
    cols = Tool.__table__.columns
    assert "source_skill_id" in cols
    assert "source_script_path" in cols
    assert "source_bundle_digest" in cols
    assert "script_network" in cols
    assert "script_network_allowlist" in cols


def test_source_skill_id_cascades_to_null_so_tools_are_not_orphaned():
    fk = list(Tool.__table__.columns["source_skill_id"].foreign_keys)[0]
    assert fk.column.table.name == "skills"
    assert fk.ondelete == "SET NULL"


def test_script_shape_is_constrained_in_the_schema():
    names = {c.name for c in Tool.__table__.constraints if c.name}
    assert "ck_tools_skill_script_shape" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_script_columns.py -v`
Expected: FAIL — `KeyError: 'source_skill_id'`

- [ ] **Step 3: Write minimal implementation**

In `app/models/skill.py`, add `CheckConstraint` to the sqlalchemy import list, then inside `class Tool` add before `def __repr__`:

```python
    # --- promoted skill script (NULL source_skill_id => an ordinary pool tool) ---
    source_skill_id = Column(
        Integer, ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_script_path = Column(String(500), nullable=True)   # e.g. scripts/triage.py
    source_bundle_digest = Column(String(64), nullable=True)  # bundle sha256 at approval
    script_network = Column(String(20), nullable=True)        # none | allowlist
    script_network_allowlist = Column(JSON, nullable=True)    # List[str], phase 2
```

and add the table args to the same class:

```python
    __table_args__ = (
        CheckConstraint(
            "source_skill_id IS NULL OR ("
            "source_script_path IS NOT NULL AND source_bundle_digest IS NOT NULL "
            "AND script_network IS NOT NULL)",
            name="ck_tools_skill_script_shape",
        ),
    )
```

Create `alembic/versions/038_skill_script_tools.py`:

```python
"""Promote reviewed skill bundle scripts into tools.

Revision ID: 038_skill_script_tools
Revises: 037_skill_bundle_files
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "038_skill_script_tools"
down_revision: Union[str, None] = "037_skill_bundle_files"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tools", sa.Column("source_skill_id", sa.Integer(), nullable=True))
    op.add_column("tools", sa.Column("source_script_path", sa.String(length=500), nullable=True))
    op.add_column("tools", sa.Column("source_bundle_digest", sa.String(length=64), nullable=True))
    op.add_column("tools", sa.Column("script_network", sa.String(length=20), nullable=True))
    op.add_column("tools", sa.Column("script_network_allowlist", sa.JSON(), nullable=True))
    op.create_index("ix_tools_source_skill_id", "tools", ["source_skill_id"])
    op.create_foreign_key(
        "fk_tools_source_skill_id_skills", "tools", "skills",
        ["source_skill_id"], ["id"], ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_tools_skill_script_shape", "tools",
        "source_skill_id IS NULL OR ("
        "source_script_path IS NOT NULL AND source_bundle_digest IS NOT NULL "
        "AND script_network IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tools_skill_script_shape", "tools", type_="check")
    op.drop_constraint("fk_tools_source_skill_id_skills", "tools", type_="foreignkey")
    op.drop_index("ix_tools_source_skill_id", table_name="tools")
    for col in ("script_network_allowlist", "script_network", "source_bundle_digest",
                "source_script_path", "source_skill_id"):
        op.drop_column("tools", col)
```

- [ ] **Step 4: Run tests and apply the migration**

Run: `.venv/bin/python -m pytest tests/test_skill_script_columns.py -v`
Expected: 3 passed

Run: `make test-env-up && DATABASE_URL=postgresql+asyncpg://postgres:cyberguard-test-only@localhost:55432/cyberguard_test REDIS_URL=redis://:cyberguard-test-only@localhost:56379/0 REDIS_PASSWORD=cyberguard-test-only ENCRYPTION_KEY=$(python3 -c "print('0'*64)") SECRET_KEY=$(python3 -c "print('1'*64)") ENVIRONMENT=testing .venv/bin/python -m alembic upgrade head`
Expected: `Running upgrade 037_skill_bundle_files -> 038_skill_script_tools`

- [ ] **Step 5: Commit**

```bash
git add app/models/skill.py alembic/versions/038_skill_script_tools.py tests/test_skill_script_columns.py
git commit -m "feat: add promoted-script columns to tools"
```

---

### Task 4: `SKILL_SCRIPT_APPROVE` permission

**Files:**
- Modify: `app/core/rbac.py`
- Test: `tests/test_skill_script_rbac.py`

**Interfaces:**
- Produces: `Permission.SKILL_SCRIPT_APPROVE` (value `"skill:script_approve"`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_script_rbac.py`:

```python
"""Uploading a script and letting it execute must be separately revocable."""
from __future__ import annotations

from app.core.rbac import Permission, Role, ROLE_PERMISSIONS, has_permission


def test_only_admin_may_approve_skill_scripts():
    for role in Role:
        expected = role is Role.ADMIN
        assert has_permission(role, Permission.SKILL_SCRIPT_APPROVE) is expected


def test_approval_is_not_implied_by_skill_write():
    # They happen to coincide on ADMIN today. The point is that a future role
    # can hold SKILL_WRITE without silently gaining code execution.
    for role, perms in ROLE_PERMISSIONS.items():
        if Permission.SKILL_WRITE in perms and role is not Role.ADMIN:
            assert Permission.SKILL_SCRIPT_APPROVE not in perms
    assert Permission.SKILL_SCRIPT_APPROVE is not Permission.SKILL_WRITE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_script_rbac.py -v`
Expected: FAIL — `AttributeError: SKILL_SCRIPT_APPROVE`

- [ ] **Step 3: Write minimal implementation**

In `app/core/rbac.py`, under the `# Skill/Tool` block:

```python
    SKILL_READ = "skill:read"
    SKILL_WRITE = "skill:write"
    # Promoting a bundle script to an executable Tool. Deliberately separate
    # from SKILL_WRITE: uploading a script and granting it the right to run
    # must be two independently revocable capabilities.
    SKILL_SCRIPT_APPROVE = "skill:script_approve"
```

and in `ROLE_PERMISSIONS[Role.ADMIN]` change the skill line to:

```python
        Permission.SKILL_READ, Permission.SKILL_WRITE, Permission.SKILL_SCRIPT_APPROVE,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_skill_script_rbac.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add app/core/rbac.py tests/test_skill_script_rbac.py
git commit -m "feat: add skill:script_approve permission"
```

---

### Task 5: `skill_runner` materialization

**Files:**
- Create: `skill_runner/__init__.py`, `skill_runner/materialize.py`
- Test: `tests/test_skill_runner_materialize.py`

**Interfaces:**
- Consumes: nothing from `app` — this package is standalone
- Produces:
  - `MaterializeError(Exception)`
  - `safe_relative_path(name: str) -> str`
  - `materialize(files: list[dict], root: str) -> tuple[str, str]` returning `(bundle_dir, scratch_dir)`; each `files` entry is `{"path": str, "content_b64": str}`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_runner_materialize.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_runner_materialize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_runner'`

- [ ] **Step 3: Write minimal implementation**

Create `skill_runner/__init__.py` (empty file).

Create `skill_runner/materialize.py`:

```python
"""Write a skill bundle into a throwaway directory, safely.

Standalone by design: this package must not import from ``app`` (mirroring the
rule ``tool_runner`` already follows), so the path rules are restated here
rather than shared with the importer.
"""
from __future__ import annotations

import base64
import os
import re
import stat
from typing import Any, Dict, List, Tuple


class MaterializeError(Exception):
    """A bundle payload violated a path or size rule."""


def safe_relative_path(name: str) -> str:
    """Normalize a bundle path, refusing anything that escapes the root."""
    normalized = (name or "").replace("\\", "/")
    if not normalized:
        raise MaterializeError("empty path in bundle")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        raise MaterializeError(f"absolute path in bundle: {name}")
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise MaterializeError(f"path traversal in bundle: {name}")
    if not parts:
        raise MaterializeError(f"empty path in bundle: {name}")
    return "/".join(parts)


def materialize(files: List[Dict[str, Any]], root: str) -> Tuple[str, str]:
    """Write ``files`` under ``root/bundle`` and create ``root/scratch``.

    Returns ``(bundle_dir, scratch_dir)``. The bundle tree is left read-only;
    the scratch dir is the only place the script may write.
    """
    bundle = os.path.join(root, "bundle")
    scratch = os.path.join(root, "scratch")
    os.makedirs(bundle, exist_ok=True)
    os.makedirs(scratch, exist_ok=True)

    written: List[str] = []
    for entry in files or []:
        rel = safe_relative_path(entry.get("path", ""))
        target = os.path.join(bundle, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            payload = base64.b64decode(entry.get("content_b64") or "", validate=True)
        except Exception as e:
            raise MaterializeError(f"undecodable content for {rel}: {e}") from e
        with open(target, "wb") as fh:
            fh.write(payload)
        written.append(target)

    # Read + execute only. Directories keep +x so they stay traversable.
    for path in written:
        os.chmod(path, stat.S_IRUSR | stat.S_IXUSR)
    for dirpath, dirnames, _ in os.walk(bundle):
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), stat.S_IRUSR | stat.S_IXUSR)
    os.chmod(bundle, stat.S_IRUSR | stat.S_IXUSR)
    os.chmod(scratch, stat.S_IRWXU)
    return bundle, scratch
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_skill_runner_materialize.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add skill_runner/__init__.py skill_runner/materialize.py tests/test_skill_runner_materialize.py
git commit -m "feat: add skill bundle materialization for the sandbox runner"
```

---

### Task 6: `skill_runner` service

**Files:**
- Create: `skill_runner/main.py`
- Test: `tests/test_skill_runner_endpoints.py`

**Interfaces:**
- Consumes: `skill_runner.materialize.materialize`, `MaterializeError`
- Produces: FastAPI `app` with `GET /health` and `POST /run`.
  Request: `{"argv": [str], "timeout": int, "files": [{"path": str, "content_b64": str}]}` with header `X-Skill-Runner-Token`.
  Response: `{"stdout", "stderr", "exit_code", "duration_ms", "timed_out"}` — same shape as `tool_runner`'s `/run`.
  Also exports `ALLOWED_INTERPRETERS: frozenset[str]`, `MINIMAL_ENV_BASE: dict[str, str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_runner_endpoints.py`:

```python
"""The sandbox runner: argv restrictions, secret-free env, cleanup."""
import base64
import os
import unittest

os.environ["SKILL_RUNNER_TOKEN"] = "skill-test-token"  # before importing the app

from fastapi.testclient import TestClient

from skill_runner.main import app

_HDR = {"X-Skill-Runner-Token": "skill-test-token"}


def _f(path: str, body: str) -> dict:
    return {"path": path, "content_b64": base64.b64encode(body.encode()).decode()}


class TestSkillRunner(unittest.TestCase):
    def setUp(self):
        self._ctx = TestClient(app)
        self.client = self._ctx.__enter__()

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def _run(self, **body):
        return self.client.post("/run", json=body, headers=_HDR)

    def test_requires_its_own_token(self):
        r = self.client.post("/run", json={"argv": ["python3", "x.py"]})
        self.assertEqual(r.status_code, 401)

    def test_runs_a_script_from_the_bundle(self):
        r = self._run(argv=["python3", "scripts/x.py", "world"],
                      timeout=20, files=[_f("scripts/x.py", "import sys; print('hi', sys.argv[1])")])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["stdout"].strip(), "hi world")
        self.assertEqual(r.json()["exit_code"], 0)

    def test_script_can_read_its_sibling_bundle_files(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py", "print(open('refs/a.txt').read().strip())"),
            _f("refs/a.txt", "sibling-ok"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "sibling-ok")

    def test_child_environment_carries_no_token(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py",
               "import os; print([k for k in os.environ if 'TOKEN' in k.upper()])"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "[]")

    def test_script_may_write_only_to_scratch(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20, files=[
            _f("scripts/x.py",
               "import os\n"
               "open(os.path.join(os.environ['TMPDIR'], 'out.txt'), 'w').write('ok')\n"
               "try:\n"
               "    open('scripts/x.py', 'a').write('tampered')\n"
               "    print('BUNDLE WRITABLE')\n"
               "except OSError:\n"
               "    print('bundle read-only')\n"),
        ])
        self.assertEqual(r.json()["stdout"].strip(), "bundle read-only")

    def test_rejects_interpreters_other_than_python3_and_sh(self):
        r = self._run(argv=["/bin/cat", "scripts/x.py"], timeout=20,
                      files=[_f("scripts/x.py", "print(1)")])
        self.assertEqual(r.status_code, 400)

    def test_rejects_interpreter_flags(self):
        # python3 -c would let the caller carry its own inline program.
        r = self._run(argv=["python3", "-c", "print(1)"], timeout=20, files=[])
        self.assertEqual(r.status_code, 400)

    def test_rejects_an_entrypoint_missing_from_the_bundle(self):
        r = self._run(argv=["python3", "scripts/nope.py"], timeout=20,
                      files=[_f("scripts/x.py", "print(1)")])
        self.assertEqual(r.status_code, 400)

    def test_rejects_traversal_in_the_payload(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20,
                      files=[{"path": "../evil.py", "content_b64": ""}])
        self.assertEqual(r.status_code, 400)

    def test_timeout_kills_the_script(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=1,
                      files=[_f("scripts/x.py", "import time; time.sleep(30)")])
        self.assertTrue(r.json()["timed_out"])

    def test_temp_root_is_removed_afterwards(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=20,
                      files=[_f("scripts/x.py", "import os; print(os.getcwd())")])
        cwd = r.json()["stdout"].strip()
        self.assertTrue(cwd)
        self.assertFalse(os.path.exists(cwd))

    def test_temp_root_is_removed_after_a_timeout_too(self):
        r = self._run(argv=["python3", "scripts/x.py"], timeout=1, files=[
            _f("scripts/x.py",
               "import os, sys, time; sys.stderr.write(os.getcwd()); "
               "sys.stderr.flush(); time.sleep(30)"),
        ])
        self.assertTrue(r.json()["timed_out"])
        leaked = r.json()["stderr"].strip()
        if leaked:
            self.assertFalse(os.path.exists(leaked))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_runner_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'skill_runner.main'`

- [ ] **Step 3: Write minimal implementation**

Create `skill_runner/main.py`:

```python
"""Sandbox runner for promoted skill scripts.

Separate from tool-runner on purpose. Its token unlocks only "run a script in an
empty, network-isolated sandbox" — which is what the caller is already doing — so
stealing it buys nothing. The tool-runner token, by contrast, buys arbitrary argv
on a container that can reach the database.
"""
import asyncio
import os
import shutil
import signal
import tempfile
import time

from fastapi import FastAPI, Header, HTTPException

from skill_runner.materialize import MaterializeError, materialize, safe_relative_path

app = FastAPI(title="skill-runner")

SKILL_RUNNER_TOKEN = os.environ.get("SKILL_RUNNER_TOKEN", "")
if not SKILL_RUNNER_TOKEN:
    raise RuntimeError("SKILL_RUNNER_TOKEN must be set for the skill-runner")

OUTPUT_MAX_BYTES = 64_000
ALLOWED_INTERPRETERS = frozenset({"python3", "sh"})

# No token, no secret. See the spec's §1.1: an inherited environment is how a
# sandboxed process trades up into broader authority.
MINIMAL_ENV_BASE = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "LANG": os.environ.get("LANG", "C.UTF-8"),
    "PYTHONDONTWRITEBYTECODE": "1",
}


@app.get("/health")
async def health():
    return {"status": "ok"}


def _validate_argv(argv, files) -> str:
    """Enforce [interpreter, script_path, *args] and return the script path."""
    if not argv or not isinstance(argv, list):
        raise HTTPException(status_code=400, detail="argv must be a non-empty list")
    if argv[0] not in ALLOWED_INTERPRETERS:
        raise HTTPException(
            status_code=400,
            detail=f"interpreter must be one of {sorted(ALLOWED_INTERPRETERS)}",
        )
    if len(argv) < 2:
        raise HTTPException(status_code=400, detail="argv must name a script to run")
    script = argv[1]
    if script.startswith("-"):
        # `python3 -c ...` would let the caller carry its own inline program,
        # which is exactly what promotion review is supposed to have seen.
        raise HTTPException(status_code=400, detail="interpreter flags are not permitted")
    try:
        script = safe_relative_path(script)
    except MaterializeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    known = {safe_relative_path(f.get("path", "")) for f in (files or [])}
    if script not in known:
        raise HTTPException(status_code=400, detail=f"script not in bundle: {script}")
    return script


@app.post("/run")
async def run(body: dict, x_skill_runner_token: str = Header(default="")):
    if x_skill_runner_token != SKILL_RUNNER_TOKEN:
        raise HTTPException(status_code=401, detail="bad skill runner token")

    argv = body.get("argv") or []
    files = body.get("files") or []
    timeout = int(body.get("timeout") or 60)

    try:
        _validate_argv(argv, files)
    except MaterializeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    root = tempfile.mkdtemp(prefix="skill-", dir="/tmp")
    try:
        try:
            bundle, scratch = materialize(files, root)
        except MaterializeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"cannot write bundle: {e}") from e

        env = dict(MINIMAL_ENV_BASE, HOME=scratch, TMPDIR=scratch)
        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, cwd=bundle, env=env,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                start_new_session=True)
        except FileNotFoundError:
            return {"stdout": "", "stderr": f"interpreter not found: {argv[0]}",
                    "exit_code": 127, "duration_ms": 0, "timed_out": False}

        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                proc.kill()
            out, err = await proc.communicate()
            timed_out = True

        return {
            "stdout": (out or b"").decode("utf-8", "replace")[:OUTPUT_MAX_BYTES],
            "stderr": (err or b"").decode("utf-8", "replace")[:OUTPUT_MAX_BYTES],
            "exit_code": proc.returncode,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "timed_out": timed_out,
        }
    finally:
        # Read-only dirs need to be walkable again before they can be removed.
        shutil.rmtree(root, ignore_errors=True)
        if os.path.exists(root):
            for dirpath, dirnames, _ in os.walk(root):
                for d in dirnames:
                    os.chmod(os.path.join(dirpath, d), 0o700)
            shutil.rmtree(root, ignore_errors=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_skill_runner_endpoints.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add skill_runner/main.py tests/test_skill_runner_endpoints.py
git commit -m "feat: add the skill-runner sandbox service"
```

---

### Task 7: Image, compose service, network split

**Files:**
- Create: `skill-runner/Dockerfile`, `skill-runner/requirements.lock`
- Modify: `docker-compose.yml`
- Test: `tests/test_invariants_static.py`

**Interfaces:**
- Consumes: `skill_runner/` from Tasks 5–6
- Produces: compose service `skill-runner` on network `sandbox`; env `SKILL_RUNNER_URL=http://skill-runner:9000`, `SKILL_RUNNER_TOKEN` on `api`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_invariants_static.py`:

```python
# --------------------------------------------------------------------------
# INV-40 · skill scripts run in an isolated sandbox, not beside the data plane
# --------------------------------------------------------------------------

def _compose() -> dict:
    import yaml
    return yaml.safe_load((REPO / "docker-compose.yml").read_text())


def test_inv40_skill_runner_is_sandboxed():
    """INV-40: the script sandbox must not share a network with postgres/redis."""
    compose = _compose()
    services = compose["services"]
    assert "skill-runner" in services, "skill-runner service is missing"

    sandbox_nets = set(services["skill-runner"].get("networks") or [])
    assert sandbox_nets, "skill-runner must declare its networks explicitly"

    for data_service in ("postgres", "redis"):
        shared = sandbox_nets & set(services[data_service].get("networks") or [])
        assert not shared, (
            f"skill-runner shares network {shared} with {data_service}"
        )

    # The sandbox segment must have no route off the host network.
    for net in sandbox_nets:
        assert compose["networks"][net].get("internal") is True, (
            f"network {net} must be internal: true"
        )


def test_inv40_skill_runner_does_not_receive_the_tool_runner_token():
    services = _compose()["services"]
    env = services["skill-runner"].get("environment") or {}
    keys = set(env if isinstance(env, dict) else [e.split("=", 1)[0] for e in env])
    assert "RUNNER_TOKEN" not in keys, "skill-runner must not hold the tool-runner token"
    assert "SKILL_RUNNER_TOKEN" in keys


def test_inv40_skill_runner_package_is_standalone():
    """It must not import app/agent_core, same rule tool_runner follows."""
    offenders = []
    for path in _py_files(REPO / "skill_runner"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if m.split(".")[0] in ("app", "agent_core", "tool_runner"):
                    offenders.append(f"{path.relative_to(REPO)}: {m}")
    assert offenders == [], "INV-40 violated:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_invariants_static.py -k inv40 -v`
Expected: FAIL — `skill-runner service is missing`

- [ ] **Step 3: Write minimal implementation**

Create `skill-runner/requirements.lock` by copying `tool-runner/requirements.lock` verbatim (the service needs the same FastAPI/uvicorn stack and nothing else).

Create `skill-runner/Dockerfile`:

```dockerfile
FROM python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534

WORKDIR /app

COPY skill-runner/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --upgrade 'setuptools>=84.0.0' \
    && pip install --no-cache-dir -r requirements.lock

# Deliberately no security-tool layer. Promoted skill scripts get python3 + sh
# and the standard library; anything more belongs in the tool pool, where it is
# described by a command_template and reviewed as such.
COPY skill_runner/ ./skill_runner/

ENV PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 10001 cyberguard \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin cyberguard

USER 10001:10001

EXPOSE 9000
CMD ["uvicorn", "skill_runner.main:app", "--host", "0.0.0.0", "--port", "9000"]
```

In `docker-compose.yml`:

1. Add a `networks:` key to **every existing service** listing `- backend`, except `skill-runner`.
2. Add `- sandbox` to the `api` service's networks (api needs to reach both).
3. Add to the `api` service's `environment:` block, next to `TOOL_RUNNER_URL`:

```yaml
      SKILL_RUNNER_URL: http://skill-runner:9000
      SKILL_RUNNER_TOKEN: ${SKILL_RUNNER_TOKEN:?Set SKILL_RUNNER_TOKEN in .env}
```

4. Add the service after `tool-runner`:

```yaml
  skill-runner:
    image: cyberguard-skill-runner:1.0.0-rc.1
    build:
      context: .
      dockerfile: skill-runner/Dockerfile
    environment:
      SKILL_RUNNER_TOKEN: ${SKILL_RUNNER_TOKEN:?Set SKILL_RUNNER_TOKEN in .env}
    # Deliberately no env_file: this container must never see the app's secrets.
    # Only `sandbox`, which is internal: true — no postgres, no redis, no egress.
    networks:
      - sandbox
    tmpfs:
      - /tmp:uid=10001,gid=10001,mode=1777,size=64m
    pids_limit: 128
    mem_limit: 512m
    cpus: 1.0
    <<: *app-hardening
    restart: unless-stopped
```

5. Add at the bottom of the file, before `volumes:`:

```yaml
networks:
  backend:
  # api reaches skill-runner here. Compose network membership is bidirectional,
  # so api:8000 stays reachable from a script — see §5.3.1 of the design. What
  # this removes is postgres, redis, and all egress.
  sandbox:
    internal: true
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_invariants_static.py -k inv40 -v`
Expected: 3 passed

Run: `docker compose config >/dev/null && echo COMPOSE_OK`
Expected: `COMPOSE_OK` (set `SKILL_RUNNER_TOKEN` in `.env` first if compose complains)

- [ ] **Step 5: Commit**

```bash
git add skill-runner/ docker-compose.yml tests/test_invariants_static.py
git commit -m "feat: add the skill-runner container on an internal network

INV-40: the script sandbox shares no network with postgres or redis and
holds none of the app's secrets, so a script that subverts it gains only
what it already had."
```

---

### Task 8: Promotion endpoint

**Files:**
- Modify: `app/schemas/skill.py`, `app/routers/skills.py`
- Test: `tests/test_skill_script_promotion.py`

**Interfaces:**
- Consumes: `bundle_digest_for_skill`, `load_bundle` (Task 2); `Permission.SKILL_SCRIPT_APPROVE` (Task 4); `Tool` columns (Task 3)
- Produces:
  - `SkillScriptPromoteRequest` schema
  - `async validate_promotion(db, skill_id: int, script_path: str, body) -> dict` — returns the `Tool` column dict, raises `HTTPException(400)` on any violation
  - `POST /skills/{skill_id}/promote?script_path=<path>` returning `ToolRead`

**Deviation from spec §4.4, deliberate:** the spec wrote this as
`POST /skills/{id}/files/{path}/promote`. That route cannot be matched reliably — the
`{path:path}` converter is greedy and would swallow the trailing `/promote` segment.
The script path moves to a query parameter instead. Same inputs, unambiguous routing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_script_promotion.py`:

```python
"""Promotion is the gate that makes a bundle script executable."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.skills import validate_promotion
from app.schemas.skill import SkillScriptPromoteRequest


class _Row:
    def __init__(self, path, text):
        self.path, self.content_text, self.content_blob = path, text, None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt):
        return _Result(self.rows)


def _body(**over):
    base = dict(
        name="triage-script", description="triage an alert",
        command_template="python3 scripts/triage.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        required_permission=None, action_category="observe", risk_tier="low",
        permission_level="medium", timeout_seconds=60, script_network="none",
    )
    base.update(over)
    return SkillScriptPromoteRequest(**base)


BUNDLE = [_Row("scripts/triage.py", "print('ok')"), _Row("refs/a.md", "doc")]


@pytest.mark.asyncio
async def test_promotion_pins_the_bundle_digest():
    data = await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py", _body())
    assert data["source_skill_id"] == 1
    assert data["source_script_path"] == "scripts/triage.py"
    assert len(data["source_bundle_digest"]) == 64
    assert data["script_network"] == "none"


@pytest.mark.asyncio
async def test_promotion_refuses_a_script_not_in_the_bundle():
    with pytest.raises(HTTPException, match="not in the bundle"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/nope.py", _body())


@pytest.mark.asyncio
async def test_promotion_refuses_a_non_executable_extension():
    with pytest.raises(HTTPException, match="executable"):
        await validate_promotion(_DB(BUNDLE), 1, "refs/a.md",
                                 _body(command_template="python3 refs/a.md"))


@pytest.mark.asyncio
async def test_promotion_refuses_a_disallowed_interpreter():
    with pytest.raises(HTTPException, match="interpreter"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(command_template="bash scripts/triage.py {target}"))


@pytest.mark.asyncio
async def test_promotion_refuses_interpreter_flags():
    with pytest.raises(HTTPException, match="flag"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(command_template="python3 -c print(1)"))


@pytest.mark.asyncio
async def test_promotion_refuses_a_template_pointing_at_another_script():
    with pytest.raises(HTTPException, match="must run"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(command_template="python3 refs/a.md {target}"))


@pytest.mark.asyncio
async def test_promotion_refuses_allowlist_networking_in_phase_1():
    with pytest.raises(HTTPException, match="not supported"):
        await validate_promotion(_DB(BUNDLE), 1, "scripts/triage.py",
                                 _body(script_network="allowlist"))


@pytest.mark.asyncio
async def test_promotion_refuses_a_placeholder_absent_from_the_schema():
    # build_argv already enforces this; failing here means the approver sees it
    # at review time instead of at first execution.
    with pytest.raises(HTTPException):
        await validate_promotion(
            _DB(BUNDLE), 1, "scripts/triage.py",
            _body(command_template="python3 scripts/triage.py {undeclared}"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_script_promotion.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_promotion'`

- [ ] **Step 3: Write minimal implementation**

In `app/schemas/skill.py`, append:

```python
class SkillScriptPromoteRequest(BaseModel):
    """Admin-supplied risk metadata for promoting a bundle script to a Tool."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    command_template: str = Field(..., min_length=1)
    input_schema_json: Optional[str] = None
    required_permission: Optional[str] = None
    action_category: Optional[str] = None
    risk_tier: Optional[str] = None
    permission_level: str = "medium"
    timeout_seconds: int = 60
    script_network: str = "none"
```

In `app/routers/skills.py`, add near the other module constants:

```python
ALLOWED_SCRIPT_INTERPRETERS = ("python3", "sh")
EXECUTABLE_SCRIPT_SUFFIXES = (".py", ".sh")


async def validate_promotion(db: AsyncSession, skill_id: int, script_path: str, body):
    """Check a promotion request and return the Tool column dict.

    Every rule here is re-checked at execution; failing at review time means the
    approver sees the problem while they are looking at the script.
    """
    import json as _json
    import shlex

    from app.services.skill_bundle import bundle_digest, load_bundle
    from app.services.tool_executor import ToolArgError, build_argv

    if not script_path.lower().endswith(EXECUTABLE_SCRIPT_SUFFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"not an executable script: {script_path} "
                   f"(expected one of {', '.join(EXECUTABLE_SCRIPT_SUFFIXES)})",
        )
    if body.script_network != "none":
        raise HTTPException(
            status_code=400,
            detail=f"script_network={body.script_network!r} is not supported yet; "
                   "only 'none' is available in this phase",
        )

    files = await load_bundle(db, skill_id)
    if script_path not in {p for p, _ in files}:
        raise HTTPException(status_code=400, detail=f"{script_path} is not in the bundle")

    tokens = shlex.split(body.command_template)
    if not tokens or tokens[0] not in ALLOWED_SCRIPT_INTERPRETERS:
        raise HTTPException(
            status_code=400,
            detail=f"interpreter must be one of {', '.join(ALLOWED_SCRIPT_INTERPRETERS)}",
        )
    if len(tokens) < 2:
        raise HTTPException(status_code=400, detail="command_template must name the script")
    if tokens[1].startswith("-"):
        raise HTTPException(status_code=400, detail="interpreter flags are not permitted")
    if tokens[1] != script_path:
        raise HTTPException(
            status_code=400,
            detail=f"command_template must run {script_path}, not {tokens[1]}",
        )

    # Dry-run the real argv builder so placeholder mistakes surface at review.
    try:
        schema = _json.loads(body.input_schema_json) if body.input_schema_json else {}
    except _json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"input_schema_json is not JSON: {e}") from e
    probe = {k: "probe" for k in (schema.get("properties") or {})}
    try:
        build_argv(body.command_template, schema, probe)
    except ToolArgError as e:
        raise HTTPException(status_code=400, detail=f"command_template: {e}") from e

    return {
        "name": body.name,
        "description": body.description,
        "command_template": body.command_template,
        "input_schema_json": body.input_schema_json,
        "required_permission": body.required_permission,
        "action_category": body.action_category,
        "risk_tier": body.risk_tier,
        "permission_level": body.permission_level,
        "timeout_seconds": body.timeout_seconds,
        "is_active": True,
        "source_skill_id": skill_id,
        "source_script_path": script_path,
        "source_bundle_digest": bundle_digest(files),
        "script_network": body.script_network,
        "script_network_allowlist": None,
    }
```

Then add the endpoint (place it directly after `get_skill_file`):

```python
@router.post("/skills/{skill_id}/promote", response_model=ToolRead,
             status_code=status.HTTP_201_CREATED)
async def promote_skill_script(
    skill_id: int,
    script_path: str,
    body: SkillScriptPromoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission(Permission.SKILL_SCRIPT_APPROVE)),
):
    """Promote one reviewed bundle script into an executable Tool."""
    from app.core.audit import record_action

    skill = (await db.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if (await db.execute(select(Tool).where(Tool.name == body.name))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tool name already exists")

    data = await validate_promotion(db, skill_id, script_path, body)
    tool = Tool(**data)
    db.add(tool)
    await db.commit()
    await db.refresh(tool)

    await record_action(
        user_id=current_user.user_id, action="skill.script.promote",
        action_category=data.get("action_category"), risk_tier=data.get("risk_tier"),
        human_reviewer=str(current_user.user_id),
        input_data={"skill_id": skill_id, "script_path": script_path,
                    "digest": data["source_bundle_digest"]},
        output_data={"tool_id": tool.id, "tool_name": tool.name},
    )
    return ToolRead.model_validate(tool)
```

Add `SkillScriptPromoteRequest` to the `app.schemas.skill` import block at the top of the router.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_skill_script_promotion.py tests/test_skill_import.py -v`
Expected: 8 + 32 passed

- [ ] **Step 5: Commit**

```bash
git add app/schemas/skill.py app/routers/skills.py tests/test_skill_script_promotion.py
git commit -m "feat: promote a reviewed bundle script to a tool"
```

---

### Task 9: Re-import invalidates dependent tools

**Files:**
- Modify: `app/routers/skills.py` (`_upsert_skill`)
- Test: `tests/test_skill_script_invalidation.py`

**Interfaces:**
- Consumes: `bundle_digest` (Task 2), `Tool` columns (Task 3)
- Produces: `async invalidate_stale_script_tools(db, skill_id: int, digest: str) -> list[Tool]`; `_upsert_skill` now calls it

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_script_invalidation.py`:

```python
"""A re-import must not launder new code through an old approval."""
from __future__ import annotations

import pytest

from app.models.skill import Tool
from app.routers.skills import invalidate_stale_script_tools


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _DB:
    def __init__(self, tools):
        self.tools = tools

    async def execute(self, _stmt):
        return _Result(self.tools)


def _tool(name, digest, active=True):
    t = Tool(name=name, source_skill_id=1, source_script_path="scripts/x.py",
             source_bundle_digest=digest, script_network="none", is_active=active)
    t.id = abs(hash(name)) % 1000
    return t


@pytest.mark.asyncio
async def test_a_changed_bundle_deactivates_its_tools():
    stale = _tool("stale", "a" * 64)
    db = _DB([stale])
    changed = await invalidate_stale_script_tools(db, 1, "b" * 64)
    assert [t.name for t in changed] == ["stale"]
    assert stale.is_active is False


@pytest.mark.asyncio
async def test_an_unchanged_bundle_leaves_tools_alone():
    same = _tool("same", "c" * 64)
    changed = await invalidate_stale_script_tools(_DB([same]), 1, "c" * 64)
    assert changed == []
    assert same.is_active is True


@pytest.mark.asyncio
async def test_already_inactive_tools_are_not_reported_again():
    off = _tool("off", "a" * 64, active=False)
    assert await invalidate_stale_script_tools(_DB([off]), 1, "b" * 64) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_script_invalidation.py -v`
Expected: FAIL — `ImportError: cannot import name 'invalidate_stale_script_tools'`

- [ ] **Step 3: Write minimal implementation**

In `app/routers/skills.py`, add above `_upsert_skill`:

```python
async def invalidate_stale_script_tools(db: AsyncSession, skill_id: int, digest: str):
    """Deactivate promoted tools whose approved bundle no longer matches.

    Approval binds to a specific bundle. When the bundle changes, the approval
    no longer covers the code that would run, so the tool goes dormant until an
    admin reviews it again. Failing here means failing visibly at import time
    rather than quietly at some later execution.
    """
    rows = (
        await db.execute(
            select(Tool).where(Tool.source_skill_id == skill_id, Tool.is_active.is_(True))
        )
    ).scalars().all()
    stale = [t for t in rows if t.source_bundle_digest != digest]
    for tool in stale:
        tool.is_active = False
    return stale
```

In `_upsert_skill`, after the bundle files are added, replace the `return skill` with:

```python
    from app.services.skill_bundle import bundle_digest

    digest = bundle_digest([(f["path"], _entry_bytes(f)) for f in (files or [])])
    for stale in await invalidate_stale_script_tools(db, skill.id, digest):
        from app.core.audit import record_action
        await record_action(
            user_id=0, action="skill.script.invalidate",
            input_data={"skill_id": skill.id, "tool_id": stale.id,
                        "approved_digest": stale.source_bundle_digest,
                        "current_digest": digest},
            output_data={"deactivated": True},
        )
    return skill
```

and add the small helper next to it:

```python
def _entry_bytes(entry: Dict[str, Any]) -> bytes:
    """Bytes of an importer file entry, whichever column it is destined for."""
    if entry.get("content_text") is not None:
        return entry["content_text"].encode("utf-8")
    return entry.get("content_blob") or b""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_skill_script_invalidation.py tests/test_skill_import.py -v`
Expected: 3 + 32 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/skills.py tests/test_skill_script_invalidation.py
git commit -m "feat: deactivate promoted tools when their bundle changes"
```

---

### Task 10: Execution routing

**Files:**
- Modify: `app/services/tool_executor.py`
- Test: `tests/test_skill_script_execution.py`

**Interfaces:**
- Consumes: everything above
- Produces: `SKILL_RUNNER_URL`, `SKILL_RUNNER_TOKEN` module constants; `async _execute_skill_script(tool, argv, timeout) -> dict`; `_pool_execute` routes on `tool.source_skill_id`

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_script_execution.py`:

```python
"""Skill scripts take the same gate chain and a different runner."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.tool_executor as te


class _Resp:
    status_code = 200

    @staticmethod
    def json():
        return {"stdout": "ok", "stderr": "", "exit_code": 0,
                "duration_ms": 5, "timed_out": False}


class _Client:
    """Records where the executor posted and what it sent."""

    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.calls.append({"url": url, "json": json, "headers": headers})
        return _Resp()


def _script_tool(**over):
    base = dict(
        name="triage-script", source_skill_id=7, source_script_path="scripts/x.py",
        source_bundle_digest=None, script_network="none",
        command_template="python3 scripts/x.py {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        timeout_seconds=30, action_category="observe", rollback_command_template=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr(te.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(te, "SKILL_RUNNER_URL", "http://skill-runner:9000")
    monkeypatch.setattr(te, "SKILL_RUNNER_TOKEN", "skill-token")
    monkeypatch.setattr(te, "TOOL_RUNNER_URL", "http://tool-runner:9000")
    monkeypatch.setattr(te, "RUNNER_TOKEN", "tool-token")


def _loader(files):
    async def _load(_skill_id):
        return files

    return _load


@pytest.mark.asyncio
async def test_a_script_tool_goes_to_the_skill_runner_with_its_bundle(monkeypatch):
    files = [("scripts/x.py", b"print('ok')"), ("refs/a.md", b"doc")]
    from app.services import skill_bundle

    digest = skill_bundle.bundle_digest(files)
    monkeypatch.setattr(te, "_load_bundle_for_tool", _loader(files))

    tool = _script_tool(source_bundle_digest=digest)
    result = await te._pool_execute(
        SimpleNamespace(tool=tool, user_id=1, metadata={}), {"target": "1.2.3.4"})

    assert result["status"] == "completed"
    call = _Client.calls[-1]
    assert call["url"] == "http://skill-runner:9000/run"
    assert call["headers"]["X-Skill-Runner-Token"] == "skill-token"
    assert "X-Runner-Token" not in call["headers"]
    assert call["json"]["argv"] == ["python3", "scripts/x.py", "1.2.3.4"]
    assert {f["path"] for f in call["json"]["files"]} == {"scripts/x.py", "refs/a.md"}


@pytest.mark.asyncio
async def test_a_changed_bundle_refuses_to_execute(monkeypatch):
    monkeypatch.setattr(
        te, "_load_bundle_for_tool", _loader([("scripts/x.py", b"print('EVIL')")]))

    tool = _script_tool(source_bundle_digest="a" * 64)
    result = await te._pool_execute(
        SimpleNamespace(tool=tool, user_id=1, metadata={}), {"target": "x"})

    assert result["status"] == "error"
    assert "approval" in result["error"].lower()
    assert _Client.calls == []  # nothing was sent anywhere


@pytest.mark.asyncio
async def test_an_ordinary_tool_still_goes_to_the_tool_runner():
    tool = SimpleNamespace(
        name="nmap-scan", source_skill_id=None, command_template="nmap {target}",
        input_schema_json='{"properties": {"target": {"type": "string"}}}',
        timeout_seconds=30, action_category="observe", rollback_command_template=None)
    result = await te._pool_execute(
        SimpleNamespace(tool=tool, user_id=1, metadata={}), {"target": "1.2.3.4"})

    assert result["status"] == "completed"
    call = _Client.calls[-1]
    assert call["url"] == "http://tool-runner:9000/run"
    assert call["headers"]["X-Runner-Token"] == "tool-token"
    assert "files" not in call["json"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_skill_script_execution.py -v`
Expected: FAIL — `AttributeError: module 'app.services.tool_executor' has no attribute 'SKILL_RUNNER_URL'`

- [ ] **Step 3: Write minimal implementation**

In `app/services/tool_executor.py`, next to `TOOL_RUNNER_URL`:

```python
SKILL_RUNNER_URL = os.environ.get("SKILL_RUNNER_URL", "http://skill-runner:9000")
SKILL_RUNNER_TOKEN = os.environ.get("SKILL_RUNNER_TOKEN", "")
```

Add above `_pool_execute`:

```python
async def _load_bundle_for_tool(skill_id: int):
    """Load a skill's bundle, owning the session.

    It opens its own session rather than taking one so that a unit test can
    replace this single function and need no database at all.
    """
    from app.core.database import get_db_context
    from app.services.skill_bundle import load_bundle

    async with get_db_context() as db:
        return await load_bundle(db, skill_id)


async def _execute_skill_script(tool, argv: List[str], timeout: int) -> Dict[str, Any]:
    """Verify the bundle still matches the approval, then run it in the sandbox."""
    import base64

    from app.services.skill_bundle import bundle_digest

    files = await _load_bundle_for_tool(tool.source_skill_id)

    if bundle_digest(files) != (tool.source_bundle_digest or ""):
        return {
            "status": "error",
            "is_error": True,
            "error": "skill bundle has changed since approval; the tool must be "
                     "reviewed and promoted again before it can run",
        }

    payload = {
        "argv": argv,
        "timeout": timeout,
        "files": [
            {"path": path, "content_b64": base64.b64encode(content).decode()}
            for path, content in files
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout + 10) as client:
            r = await client.post(
                f"{SKILL_RUNNER_URL}/run", json=payload,
                headers={"X-Skill-Runner-Token": SKILL_RUNNER_TOKEN},
            )
    except Exception as e:
        return {"status": "error", "is_error": True, "error": f"skill-runner unreachable: {e}"}

    if r.status_code != 200:
        return {"status": "error", "is_error": True,
                "error": f"skill-runner {r.status_code}: {r.text[:200]}"}

    data = r.json()
    exit_code = data.get("exit_code")
    timed_out = data.get("timed_out", False)
    is_error = bool(timed_out) or (exit_code not in (0, None))
    return {
        "status": "error" if is_error else "completed",
        "stdout": _truncate(data.get("stdout", "")),
        "stderr": _truncate(data.get("stderr", "")),
        "exit_code": exit_code,
        "duration_ms": data.get("duration_ms"),
        "timed_out": timed_out,
        "is_error": is_error,
    }
```

In `_pool_execute`, immediately after `timeout = int(...)` and **before** the safety-envelope block:

```python
    # Promoted skill scripts run in the sandbox runner. Everything above this
    # line — kill switch, RBAC, gatekeeper, approval — already ran, because a
    # promoted script is an ordinary Tool travelling the ordinary path.
    if getattr(tool, "source_skill_id", None) is not None:
        return await _execute_skill_script(tool, argv, timeout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_skill_script_execution.py tests/test_tool_executor.py -v`
Expected: 3 passed + existing tool_executor tests pass

- [ ] **Step 5: Commit**

```bash
git add app/services/tool_executor.py tests/test_skill_script_execution.py
git commit -m "feat: route promoted skill scripts to the sandbox runner"
```

---

### Task 11: Promotion UI

**Files:**
- Modify: `webui/src/api/client.ts`, `webui/src/pages/Skills.tsx`, `webui/src/i18n/en.json`, `webui/src/i18n/zh.json`
- Test: `webui` gates (`make web`)

**Interfaces:**
- Consumes: `POST /skills/{id}/promote?script_path=...`, `GET /skills/{id}/files`, `GET /skills/{id}/files/{path}`
- Produces: a promotion modal on the Skills page

- [ ] **Step 1: Add the API client methods**

In `webui/src/api/client.ts`, next to `importSkillFile`:

```typescript
  getSkillFiles: (id: number) => request(`/skills/${id}/files`),
  promoteSkillScript: (id: number, scriptPath: string, body: JsonBody) =>
    request(`/skills/${id}/promote?script_path=${encodeURIComponent(scriptPath)}`,
      { method: 'POST', body: JSON.stringify(body) }),
```

- [ ] **Step 2: Add the i18n keys**

In `webui/src/i18n/en.json` under `skills`:

```json
    "bundleFilesTitle": "Bundled files",
    "promote": "Promote to tool",
    "promoteTitle": "Promote script to tool",
    "promoteReview": "Review this script. Once promoted it becomes an executable tool, gated like any other.",
    "promoteDigestNote": "The tool is pinned to this bundle. Re-importing the skill with different contents deactivates it until you review it again.",
    "promoteNoNetwork": "Scripts run with no network access and the Python standard library only."
```

In `webui/src/i18n/zh.json` under `skills`:

```json
    "bundleFilesTitle": "附带文件",
    "promote": "核准为工具",
    "promoteTitle": "将脚本核准为工具",
    "promoteReview": "请审阅这个脚本。核准后它将成为可执行工具，与其他工具受同样的闸门约束。",
    "promoteDigestNote": "该工具绑定到当前 bundle。重新导入内容不同的同名 skill 会使其停用，直到你重新审阅。",
    "promoteNoNetwork": "脚本在无网络环境中运行，且只能使用 Python 标准库。"
```

- [ ] **Step 3: Add the promotion modal**

In `webui/src/pages/Skills.tsx`, add the types near `ImportSummary`:

```typescript
interface BundleFile {
  path: string
  size_bytes: number
  mime?: string
  is_binary: boolean
}
```

Add state next to `importSummary`:

```typescript
  const [promoteSkill, setPromoteSkill] = useState<Skill | null>(null)
  const [bundleFiles, setBundleFiles] = useState<BundleFile[]>([])
  const [promoteScript, setPromoteScript] = useState('')
  const [promoteSource, setPromoteSource] = useState('')
  const [promoteForm, setPromoteForm] = useState({
    name: '', description: '', command_template: '', input_schema_json: '',
    required_permission: '', action_category: 'observe', risk_tier: 'low',
    permission_level: 'medium', timeout_seconds: 60, script_network: 'none',
  })
  const [promoteError, setPromoteError] = useState('')
```

Add the handlers next to `importFile`:

```typescript
  const openBundle = async (s: Skill) => {
    setPromoteSkill(s); setPromoteScript(''); setPromoteSource(''); setPromoteError('')
    try {
      const r = await api.getSkillFiles(Number(s.id)) as { files?: BundleFile[] }
      setBundleFiles(r.files || [])
    } catch (e: unknown) { setPromoteError(errorMessage(e)) }
  }

  const selectScript = async (s: Skill, path: string) => {
    setPromoteScript(path); setPromoteError('')
    const token = localStorage.getItem('token')
    const r = await fetch(`${API_BASE}/skills/${s.id}/files/${path}`,
      { headers: { Authorization: `Bearer ${token}` } })
    setPromoteSource(await r.text())
    const interpreter = path.endsWith('.sh') ? 'sh' : 'python3'
    setPromoteForm(f => ({
      ...f,
      name: `${s.name}-${path.split('/').pop()?.replace(/\.(py|sh)$/, '')}`,
      command_template: `${interpreter} ${path}`,
    }))
  }

  const submitPromotion = async () => {
    if (!promoteSkill || !promoteScript) return
    setPromoteError('')
    try {
      await api.promoteSkillScript(Number(promoteSkill.id), promoteScript, {
        ...promoteForm,
        required_permission: promoteForm.required_permission || null,
        input_schema_json: promoteForm.input_schema_json || null,
      })
      setPromoteSkill(null)
    } catch (e: unknown) { setPromoteError(errorMessage(e)) }
  }
```

Import `API_BASE` alongside `api` from `../api/client` (export it there if it is not already exported).

Add the card action, next to the existing bundle badge block:

```tsx
                  {!!s.bundle_file_count && (
                    <button onClick={() => openBundle(s)} className="btn btn-secondary"
                      style={{ fontSize: 11, height: 22, padding: '0 8px' }}>
                      {t('skills.bundleFilesTitle')}
                    </button>
                  )}
```

Add the modal beside the import modal:

```tsx
      {promoteSkill && (
        <Modal width={720} title={t('skills.promoteTitle').toUpperCase()}
          onClose={() => { setPromoteSkill(null); setPromoteError('') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', lineHeight: 1.6 }}>
              {t('skills.promoteReview')} {t('skills.promoteNoNetwork')}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {bundleFiles.filter(f => /\.(py|sh)$/.test(f.path)).map(f => (
                <button key={f.path} onClick={() => selectScript(promoteSkill, f.path)}
                  className={promoteScript === f.path ? 'btn btn-primary' : 'btn btn-secondary'}
                  style={{ fontSize: 11, height: 24, padding: '0 8px' }}>
                  {f.path}
                </button>
              ))}
            </div>
            {promoteScript && (
              <>
                <pre style={{
                  maxHeight: 240, overflow: 'auto', background: 'var(--bg-base)',
                  border: '1px solid var(--border)', padding: 10, fontSize: 12, margin: 0,
                }}>{promoteSource}</pre>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label className="form-label">NAME</label>
                    <input className="form-input" value={promoteForm.name}
                      onChange={e => setPromoteForm(f => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">COMMAND TEMPLATE</label>
                    <input className="form-input" value={promoteForm.command_template}
                      onChange={e => setPromoteForm(f => ({ ...f, command_template: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">ACTION CATEGORY</label>
                    <input className="form-input" value={promoteForm.action_category}
                      onChange={e => setPromoteForm(f => ({ ...f, action_category: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">RISK TIER</label>
                    <input className="form-input" value={promoteForm.risk_tier}
                      onChange={e => setPromoteForm(f => ({ ...f, risk_tier: e.target.value }))} />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label className="form-label">INPUT SCHEMA (JSON)</label>
                    <input className="form-input" value={promoteForm.input_schema_json}
                      placeholder='{"properties": {"target": {"type": "string"}}}'
                      onChange={e => setPromoteForm(f => ({ ...f, input_schema_json: e.target.value }))} />
                  </div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--amber)', lineHeight: 1.6 }}>
                  {t('skills.promoteDigestNote')}
                </div>
              </>
            )}
            {promoteError && (
              <div style={{ padding: '8px 10px', background: 'rgba(255,0,0,0.1)',
                border: '1px solid var(--red)', fontSize: 13, color: 'var(--red)' }}>
                {promoteError}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={submitPromotion} disabled={!promoteScript} className="btn btn-primary">
                {t('skills.promote').toUpperCase()}
              </button>
            </div>
          </div>
        </Modal>
      )}
```

- [ ] **Step 4: Run the frontend gates**

Run: `make web`
Expected: tsc (app + test), eslint ratchet at baseline, npm audit clean, vitest passing

- [ ] **Step 5: Commit**

```bash
git add webui/src/api/client.ts webui/src/pages/Skills.tsx webui/src/i18n/en.json webui/src/i18n/zh.json
git commit -m "feat: add the skill script promotion UI"
```

---

### Task 12: End-to-end verification and documentation

**Files:**
- Create: `tests/test_skill_script_e2e.py`
- Modify: `docs/delivery/ARCHITECTURE_AND_SECURITY.md`, `README.md`

**Interfaces:**
- Consumes: all previous tasks

- [ ] **Step 1: Write the end-to-end test**

Create `tests/test_skill_script_e2e.py`:

```python
"""Import a bundle, promote a script, execute it, then break the seal."""
from __future__ import annotations

import base64
import io
import zipfile

import pytest

from app.core.database import get_db_context
from app.models.skill import Skill, SkillFile, Tool
from app.routers import skills as skills_router
from app.schemas.skill import SkillScriptPromoteRequest
from app.services.skill_bundle import bundle_digest_for_skill
from app.services.skill_installer import install_skills_from_upload
from sqlalchemy import delete, select


SKILL_MD = "---\nname: e2e-triage\ndescription: e2e\n---\n\n# Triage\n"
SCRIPT = "import sys\nprint('triaged', sys.argv[1])\n"


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, body in entries.items():
            zf.writestr(path, body)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_import_promote_then_a_changed_bundle_breaks_the_approval():
    parsed = install_skills_from_upload("e2e.zip", _zip({
        "e2e-triage/SKILL.md": SKILL_MD,
        "e2e-triage/scripts/triage.py": SCRIPT,
    }))
    assert parsed["success"], parsed
    entry = parsed["skills"][0]

    async with get_db_context() as db:
        try:
            skill = await skills_router._upsert_skill(db, entry["skill_data"], entry["files"])
            await db.commit()
            await db.refresh(skill)

            body = SkillScriptPromoteRequest(
                name="e2e-triage-script", description="e2e",
                command_template="python3 scripts/triage.py {target}",
                input_schema_json='{"properties": {"target": {"type": "string"}}}',
                action_category="observe", risk_tier="low", script_network="none",
            )
            data = await skills_router.validate_promotion(
                db, skill.id, "scripts/triage.py", body)
            tool = Tool(**data)
            db.add(tool)
            await db.commit()
            await db.refresh(tool)

            assert tool.source_skill_id == skill.id
            assert tool.is_active is True
            assert tool.source_bundle_digest == await bundle_digest_for_skill(db, skill.id)

            # Re-import the same skill with a different script body.
            changed = install_skills_from_upload("e2e.zip", _zip({
                "e2e-triage/SKILL.md": SKILL_MD,
                "e2e-triage/scripts/triage.py": "print('DIFFERENT')\n",
            }))
            e2 = changed["skills"][0]
            await skills_router._upsert_skill(db, e2["skill_data"], e2["files"])
            await db.commit()
            await db.refresh(tool)

            assert tool.is_active is False, "approval must not survive a bundle change"
        finally:
            await db.execute(delete(Tool).where(Tool.name == "e2e-triage-script"))
            row = (await db.execute(
                select(Skill).where(Skill.name == "e2e-triage"))).scalar_one_or_none()
            if row:
                await db.execute(delete(SkillFile).where(SkillFile.skill_id == row.id))
                await db.delete(row)
            await db.commit()
```

- [ ] **Step 2: Run the whole suite**

Run: `make test`
Expected: all pass, including the 655 that passed before this plan started plus the new tests.

- [ ] **Step 3: Document the trust boundary**

Append to `docs/delivery/ARCHITECTURE_AND_SECURITY.md`:

```markdown
### Executable skill scripts

A script inside a skill bundle is inert on import. An admin holding
`skill:script_approve` reviews it and promotes it into a `Tool`, supplying the
risk metadata; from then on it is gated by the same chain as every other tool,
because it is the same object.

The `Tool` pins the sha256 of the bundle it was approved against. Re-importing
the skill with different contents deactivates the tool until it is reviewed
again, so an approval cannot be reused for code nobody read.

Scripts execute in `skill-runner`, a separate container on an `internal: true`
network: no postgres, no redis, no egress, `python3`/`sh` and the standard
library only, and an environment carrying no token or secret. `api:8000`
remains reachable from that segment — compose network membership is
bidirectional — but a script holds no credential for it.

See `docs/superpowers/specs/2026-09-15-skill-script-execution-design.md`.
```

In `README.md`, add `SKILL_RUNNER_TOKEN` to the documented required `.env` variables next to `RUNNER_TOKEN`, described as "token for the skill-script sandbox runner; must differ from RUNNER_TOKEN".

- [ ] **Step 4: Verify the full gate set**

Run: `make check`
Expected: Python suite + invariants + frontend gates all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_skill_script_e2e.py docs/delivery/ARCHITECTURE_AND_SECURITY.md README.md
git commit -m "test: end-to-end skill script promotion and seal-breaking

Covers the property the whole design exists for: an approval binds to the
bundle it was granted against and does not survive a change to it."
```

---

## Deferred to Phase 2

`script_network = "allowlist"` (spec §8) needs a `skill-runner-net` container with no default route, reaching a forward proxy that holds the domain allowlist. The columns already exist and the promotion endpoint already rejects the value, so Phase 2 adds a container and a branch — no migration, no rework of Tasks 1–12.
