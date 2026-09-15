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
