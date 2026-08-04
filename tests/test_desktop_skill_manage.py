"""Desktop skill management: draft → approve → catalog."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def skill_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CYBERGUARD_DATA_DIR", str(tmp_path))
    # Clear any cached paths if present
    yield tmp_path


def test_save_approve_appears_in_catalog(skill_data_dir):
    from apps.desktop.sidecar.skill_loader import (
        approve_skill,
        list_skills,
        list_skills_managed,
        save_draft,
        delete_managed_skill,
        get_managed_skill,
    )

    r = save_draft(
        {
            "name": "custom_triage",
            "description": "My triage SOP",
            "body": "# SOP\n\nDo triage carefully.\n",
            "version": "0.1.0",
        }
    )
    assert r["ok"] is True
    assert r["skill"]["source"] == "draft"

    inv = list_skills_managed()
    assert any(d["name"] == "custom_triage" for d in inv["drafts"])
    assert not any(s["name"] == "custom_triage" for s in inv["skills"])

    a = approve_skill("custom_triage")
    assert a["ok"] is True, a

    inv2 = list_skills_managed()
    assert any(
        s["name"] == "custom_triage" and s["source"] == "approved"
        for s in inv2["skills"]
    )
    assert not any(d["name"] == "custom_triage" for d in inv2["drafts"])

    names = {s.name for s in list_skills(include_body=False)}
    assert "custom_triage" in names

    g = get_managed_skill("custom_triage", source="approved")
    assert g["ok"] and "triage" in (g["skill"].get("body") or "").lower()

    d = delete_managed_skill("custom_triage", source="approved")
    assert d["ok"]
    names2 = {s.name for s in list_skills(include_body=False)}
    assert "custom_triage" not in names2


def test_cannot_approve_builtin_name(skill_data_dir):
    from apps.desktop.sidecar.skill_loader import (
        approve_skill,
        list_skills,
        save_draft,
    )

    builtins = [s.name for s in list_skills() if s.source == "builtin"]
    assert builtins, "expected package builtin skills"
    b = builtins[0]
    save_draft({"name": b, "description": "x", "body": "body text"})
    bad = approve_skill(b)
    assert bad["ok"] is False
    assert "builtin" in (bad.get("error") or "").lower()


def test_import_draft_from_content(skill_data_dir):
    from apps.desktop.sidecar.skill_loader import import_draft, list_skills_managed

    md = """---
name: imported_sop
description: From content
version: "2.0.0"
mode: advisory
---

# Imported

Steps here.
"""
    r = import_draft(content=md)
    assert r["ok"] is True
    assert r["skill"]["name"] == "imported_sop"
    inv = list_skills_managed()
    assert any(d["name"] == "imported_sop" for d in inv["drafts"])


def test_invalid_name_rejected(skill_data_dir):
    from apps.desktop.sidecar.skill_loader import save_draft

    r = save_draft({"name": "1bad", "description": "x", "body": "y"})
    assert r["ok"] is False
