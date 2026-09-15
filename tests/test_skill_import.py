"""Skill import: markdown, JSON, and general SKILL.md zip bundles."""
from __future__ import annotations

import io
import json
import os
import zipfile

import pytest

from app.services import skill_installer as si


def _zip(entries: dict[str, bytes | str], *, compresslevel: int | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, payload in entries.items():
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            zf.writestr(path, payload)
    return buf.getvalue()


SKILL_MD = """---
name: alert-triage
description: Triage a security alert
version: 2.1.0
category: log_analysis
tags:
  - soc
  - triage
allowed-tools:
  - Read
  - Bash
---

# Alert triage

Step 1. Read the alert.
"""


# --- frontmatter parsing ---

def test_yaml_frontmatter_parses_lists_and_keeps_extra_keys():
    meta, body = si._parse_frontmatter(SKILL_MD)
    assert meta["name"] == "alert-triage"
    assert meta["version"] == "2.1.0"
    assert meta["tags"] == ["soc", "triage"]
    assert meta["allowed-tools"] == ["Read", "Bash"]
    assert body.lstrip().startswith("# Alert triage")


def test_frontmatter_falls_back_when_yaml_is_malformed():
    bad = "---\nname: broken\ndescription: [unclosed\n---\n\nbody text\n"
    meta, body = si._parse_frontmatter(bad)
    assert meta["name"] == "broken"
    assert "body text" in body


def test_normalize_carries_tags_and_unknown_frontmatter_into_metadata():
    meta, body = si._parse_frontmatter(SKILL_MD)
    data = si._normalize_skill_data("fallback-name", meta, body)
    assert data["name"] == "alert-triage"
    assert data["version"] == "2.1.0"
    assert data["category"] == "log_analysis"
    assert data["tags"] == ["soc", "triage"]
    assert data["metadata_json"]["frontmatter"]["allowed-tools"] == ["Read", "Bash"]


# --- single-file uploads ---

def test_markdown_upload_still_works():
    result = si.install_skills_from_upload("alert-triage.md", SKILL_MD.encode("utf-8"))
    assert result["success"] is True
    assert len(result["skills"]) == 1
    assert result["skills"][0]["skill_data"]["name"] == "alert-triage"
    assert result["skills"][0]["files"] == []


def test_markdown_without_frontmatter_names_from_filename():
    result = si.install_skills_from_upload("my-sop.md", b"# just a body\n")
    assert result["success"] is True
    assert result["skills"][0]["skill_data"]["name"] == "my-sop"


def test_json_upload_is_parsed_as_json_not_markdown():
    payload = json.dumps(
        {
            "name": "json-skill",
            "description": "from json",
            "version": "3.0.0",
            "category": "threat_intel",
            "tags": ["ti"],
            "md_content": "# body from json\n",
        }
    ).encode("utf-8")
    result = si.install_skills_from_upload("json-skill.json", payload)
    assert result["success"] is True
    data = result["skills"][0]["skill_data"]
    assert data["name"] == "json-skill"
    assert data["version"] == "3.0.0"
    assert data["tags"] == ["ti"]
    assert data["md_content"].strip() == "# body from json"
    # the raw JSON must not leak into the body
    assert "md_content" not in data["md_content"]


def test_json_upload_accepts_content_alias():
    payload = json.dumps({"name": "aliased", "content": "# aliased body"}).encode("utf-8")
    result = si.install_skills_from_upload("x.json", payload)
    assert result["success"] is True
    assert result["skills"][0]["skill_data"]["md_content"].strip() == "# aliased body"


def test_json_upload_rejects_malformed_json():
    result = si.install_skills_from_upload("bad.json", b"{not json")
    assert result["success"] is False
    assert "JSON" in result["error"]


def test_non_utf8_markdown_is_rejected():
    result = si.install_skills_from_upload("x.md", b"\xff\xfe\x00bad")
    assert result["success"] is False
    assert "UTF-8" in result["error"]


# --- zip bundles ---

def test_zip_single_skill_collects_bundle_files():
    data = _zip(
        {
            "alert-triage/SKILL.md": SKILL_MD,
            "alert-triage/references/playbook.md": "# playbook\n",
            "alert-triage/scripts/run.sh": "#!/bin/sh\necho hi\n",
        }
    )
    result = si.install_skills_from_upload("bundle.zip", data)
    assert result["success"] is True
    assert len(result["skills"]) == 1
    entry = result["skills"][0]
    assert entry["skill_data"]["name"] == "alert-triage"
    paths = sorted(f["path"] for f in entry["files"])
    assert paths == ["references/playbook.md", "scripts/run.sh"]
    playbook = next(f for f in entry["files"] if f["path"] == "references/playbook.md")
    assert playbook["content_text"] == "# playbook\n"
    assert playbook["content_blob"] is None
    assert playbook["size_bytes"] == len(b"# playbook\n")


def test_zip_skill_md_at_root_is_supported():
    data = _zip({"SKILL.md": SKILL_MD, "references/a.md": "a"})
    result = si.install_skills_from_upload("alert.zip", data)
    assert result["success"] is True
    assert result["skills"][0]["skill_data"]["name"] == "alert-triage"
    assert [f["path"] for f in result["skills"][0]["files"]] == ["references/a.md"]


def test_zip_names_skill_from_directory_when_frontmatter_has_none():
    data = _zip({"repo/skills/my-dir-skill/SKILL.md": "# no frontmatter here\n"})
    result = si.install_skills_from_upload("repo.zip", data)
    assert result["success"] is True
    assert result["skills"][0]["skill_data"]["name"] == "my-dir-skill"


def test_zip_imports_every_skill_in_a_repo():
    data = _zip(
        {
            "repo/README.md": "# repo",
            "repo/skills/a/SKILL.md": "---\nname: skill-a\n---\nbody a\n",
            "repo/skills/a/references/ref.md": "ref a",
            "repo/skills/b/SKILL.md": "---\nname: skill-b\n---\nbody b\n",
        }
    )
    result = si.install_skills_from_upload("repo.zip", data)
    assert result["success"] is True
    names = sorted(s["skill_data"]["name"] for s in result["skills"])
    assert names == ["skill-a", "skill-b"]
    a = next(s for s in result["skills"] if s["skill_data"]["name"] == "skill-a")
    b = next(s for s in result["skills"] if s["skill_data"]["name"] == "skill-b")
    assert [f["path"] for f in a["files"]] == ["references/ref.md"]
    assert b["files"] == []
    # repo/README.md belongs to no skill root and must not be attached anywhere
    assert all("README" not in f["path"] for s in result["skills"] for f in s["files"])


def test_zip_nested_skill_is_not_swallowed_by_its_parent():
    data = _zip(
        {
            "outer/SKILL.md": "---\nname: outer\n---\nouter body\n",
            "outer/refs/o.md": "o",
            "outer/inner/SKILL.md": "---\nname: inner\n---\ninner body\n",
            "outer/inner/refs/i.md": "i",
        }
    )
    result = si.install_skills_from_upload("nested.zip", data)
    assert result["success"] is True
    outer = next(s for s in result["skills"] if s["skill_data"]["name"] == "outer")
    inner = next(s for s in result["skills"] if s["skill_data"]["name"] == "inner")
    assert [f["path"] for f in outer["files"]] == ["refs/o.md"]
    assert [f["path"] for f in inner["files"]] == ["refs/i.md"]


def test_zip_binary_asset_is_stored_as_blob():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 8
    data = _zip({"s/SKILL.md": "---\nname: s\n---\nbody\n", "s/assets/logo.png": png})
    result = si.install_skills_from_upload("s.zip", data)
    asset = next(f for f in result["skills"][0]["files"] if f["path"] == "assets/logo.png")
    assert asset["content_blob"] == png
    assert asset["content_text"] is None
    assert asset["mime"] == "image/png"


def test_zip_skips_macos_and_vcs_noise():
    data = _zip(
        {
            "s/SKILL.md": "---\nname: s\n---\nbody\n",
            "s/.DS_Store": "junk",
            "s/.git/config": "junk",
            "__MACOSX/s/._SKILL.md": "junk",
            "s/refs/keep.md": "keep",
        }
    )
    result = si.install_skills_from_upload("s.zip", data)
    assert len(result["skills"]) == 1
    assert [f["path"] for f in result["skills"][0]["files"]] == ["refs/keep.md"]


def test_zip_without_skill_md_falls_back_to_a_lone_markdown_file():
    data = _zip({"solo-skill.md": SKILL_MD})
    result = si.install_skills_from_upload("solo.zip", data)
    assert result["success"] is True
    assert result["skills"][0]["skill_data"]["name"] == "alert-triage"


def test_zip_with_nothing_importable_errors():
    data = _zip({"notes.txt": "hello", "image.png": b"\x89PNG"})
    result = si.install_skills_from_upload("empty.zip", data)
    assert result["success"] is False
    assert "SKILL.md" in result["error"]


def test_zip_with_several_loose_markdown_files_errors():
    data = _zip({"a.md": "# a", "b.md": "# b"})
    result = si.install_skills_from_upload("loose.zip", data)
    assert result["success"] is False
    assert "SKILL.md" in result["error"]


def test_corrupt_zip_is_rejected():
    result = si.install_skills_from_upload("bad.zip", b"PK\x03\x04garbage")
    assert result["success"] is False
    assert "zip" in result["error"].lower()


# --- zip hardening ---

def test_zip_rejects_path_traversal():
    data = _zip({"s/SKILL.md": "---\nname: s\n---\nb\n", "s/../../etc/passwd": "pwned"})
    result = si.install_skills_from_upload("evil.zip", data)
    assert result["success"] is False
    assert "path" in result["error"].lower()


def test_zip_rejects_absolute_paths():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("s/SKILL.md", "---\nname: s\n---\nb\n")
        zf.writestr("/etc/passwd", "pwned")
    result = si.install_skills_from_upload("evil.zip", buf.getvalue())
    assert result["success"] is False
    assert "path" in result["error"].lower()


def test_zip_rejects_too_many_entries():
    entries = {"s/SKILL.md": "---\nname: s\n---\nb\n"}
    for i in range(si.MAX_ZIP_ENTRIES + 1):
        entries[f"s/refs/f{i}.md"] = "x"
    result = si.install_skills_from_upload("many.zip", _zip(entries))
    assert result["success"] is False
    assert "entries" in result["error"].lower()


def test_zip_rejects_oversized_bundle_file():
    big = b"a" * (si.MAX_BUNDLE_FILE_BYTES + 1)
    data = _zip({"s/SKILL.md": "---\nname: s\n---\nb\n", "s/refs/big.txt": big})
    result = si.install_skills_from_upload("big.zip", data)
    assert result["success"] is False
    assert "too large" in result["error"].lower()


def test_zip_rejects_oversized_total_uncompressed_size():
    # Incompressible payload, so this trips the total-size guard rather than
    # the compression-ratio guard.
    chunk = os.urandom(si.MAX_BUNDLE_FILE_BYTES)
    entries = {"s/SKILL.md": "---\nname: s\n---\nb\n"}
    n = (si.MAX_UNCOMPRESSED_TOTAL_BYTES // si.MAX_BUNDLE_FILE_BYTES) + 1
    for i in range(n):
        entries[f"s/refs/f{i}.bin"] = chunk
    result = si.install_skills_from_upload("bomb.zip", _zip(entries))
    assert result["success"] is False
    assert "too large" in result["error"].lower()


def test_zip_rejects_high_compression_ratio_bomb():
    data = _zip(
        {
            "s/SKILL.md": "---\nname: s\n---\nb\n",
            "s/refs/bomb.bin": b"\x00" * si.MAX_BUNDLE_FILE_BYTES,
        }
    )
    result = si.install_skills_from_upload("bomb.zip", data)
    assert result["success"] is False
    assert "compression ratio" in result["error"].lower()


def test_zip_rejects_symlink_entries():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("s/SKILL.md", "---\nname: s\n---\nb\n")
        info = zipfile.ZipInfo("s/link")
        info.external_attr = (0o120777 << 16)  # S_IFLNK
        zf.writestr(info, "/etc/passwd")
    result = si.install_skills_from_upload("link.zip", buf.getvalue())
    assert result["success"] is False
    assert "symlink" in result["error"].lower()


def test_upload_rejects_payload_over_the_size_cap():
    result = si.install_skills_from_upload("x.md", b"a" * (si.MAX_UPLOAD_BYTES + 1))
    assert result["success"] is False
    assert "too large" in result["error"].lower()


def test_unsupported_extension_is_rejected():
    result = si.install_skills_from_upload("skill.exe", b"MZ")
    assert result["success"] is False
    assert "Unsupported" in result["error"]


# --- url install keeps its single-skill contract ---

def test_install_skill_from_content_still_returns_single_skill_shape():
    result = si.install_skill_from_content("https://x/SKILL.md", SKILL_MD)
    assert result["success"] is True
    assert result["skill_data"]["name"] == "alert-triage"


# --- router upsert semantics ---

class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Minimal AsyncSession stand-in recording adds and delete statements."""

    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.deletes = []
        self.flushed = 0

    async def execute(self, stmt):
        if stmt.is_delete:
            self.deletes.append(stmt)
            return _FakeResult(None)
        return _FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = 42

    async def flush(self):
        self.flushed += 1


@pytest.mark.asyncio
async def test_upsert_creates_skill_and_its_bundle_files():
    from app.models.skill import SkillFile
    from app.routers.skills import _upsert_skill

    db = _FakeDB(existing=None)
    result = si.install_skills_from_upload(
        "b.zip",
        _zip({"s/SKILL.md": "---\nname: s\n---\nbody\n", "s/refs/a.md": "a"}),
    )
    entry = result["skills"][0]
    skill = await _upsert_skill(db, entry["skill_data"], entry["files"])

    assert skill.name == "s"
    files = [o for o in db.added if isinstance(o, SkillFile)]
    assert [f.path for f in files] == ["refs/a.md"]
    assert files[0].skill_id == skill.id
    # the old file set is cleared even on a first insert, so re-imports are uniform
    assert len(db.deletes) == 1


@pytest.mark.asyncio
async def test_upsert_replaces_the_previous_file_set_on_reimport():
    from app.models.skill import Skill, SkillFile
    from app.routers.skills import _upsert_skill

    existing = Skill(name="s", md_content="old", version="1.0.0")
    existing.id = 7
    db = _FakeDB(existing=existing)

    result = si.install_skills_from_upload(
        "b.zip",
        _zip({"s/SKILL.md": "---\nname: s\nversion: 2.0.0\n---\nnew body\n", "s/refs/new.md": "n"}),
    )
    entry = result["skills"][0]
    skill = await _upsert_skill(db, entry["skill_data"], entry["files"])

    assert skill is existing
    assert skill.version == "2.0.0"
    assert "new body" in skill.md_content
    assert len(db.deletes) == 1  # old rows dropped before the new set is written
    assert [f.path for f in db.added if isinstance(f, SkillFile)] == ["refs/new.md"]
