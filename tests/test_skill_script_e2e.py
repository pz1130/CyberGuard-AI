"""Import a bundle, promote a script, then break the seal."""
from __future__ import annotations

import io
import zipfile

import pytest
from sqlalchemy import delete, select

from app.core.database import get_db_context
from app.models.skill import Skill, SkillFile, Tool
from app.routers import skills as skills_router
from app.schemas.skill import SkillScriptPromoteRequest
from app.services.skill_bundle import bundle_digest_for_skill
from app.services.skill_installer import install_skills_from_upload


SKILL_MD = "---\nname: e2e-triage\ndescription: e2e\n---\n\n# Triage\n"
SCRIPT = "import sys\nprint('triaged', sys.argv[1])\n"


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, body in entries.items():
            zf.writestr(path, body)
    return buf.getvalue()


async def _cleanup(db):
    await db.execute(delete(Tool).where(Tool.name == "e2e-triage-script"))
    row = (await db.execute(
        select(Skill).where(Skill.name == "e2e-triage"))).scalar_one_or_none()
    if row:
        await db.execute(delete(SkillFile).where(SkillFile.skill_id == row.id))
        await db.delete(row)
    await db.commit()


@pytest.mark.asyncio
async def test_import_promote_then_a_changed_bundle_breaks_the_approval():
    parsed = install_skills_from_upload("e2e.zip", _zip({
        "e2e-triage/SKILL.md": SKILL_MD,
        "e2e-triage/scripts/triage.py": SCRIPT,
    }))
    assert parsed["success"], parsed
    entry = parsed["skills"][0]

    async with get_db_context() as db:
        await _cleanup(db)
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
            await _cleanup(db)


@pytest.mark.asyncio
async def test_deleting_a_skill_does_not_orphan_its_promoted_tool():
    parsed = install_skills_from_upload("e2e.zip", _zip({
        "e2e-triage/SKILL.md": SKILL_MD,
        "e2e-triage/scripts/triage.py": SCRIPT,
    }))
    entry = parsed["skills"][0]

    async with get_db_context() as db:
        await _cleanup(db)
        try:
            skill = await skills_router._upsert_skill(db, entry["skill_data"], entry["files"])
            await db.commit()
            await db.refresh(skill)

            data = await skills_router.validate_promotion(
                db, skill.id, "scripts/triage.py",
                SkillScriptPromoteRequest(
                    name="e2e-triage-script",
                    command_template="python3 scripts/triage.py {target}",
                    input_schema_json='{"properties": {"target": {"type": "string"}}}',
                    script_network="none"))
            tool = Tool(**data)
            db.add(tool)
            await db.commit()
            await db.refresh(tool)

            await db.execute(delete(SkillFile).where(SkillFile.skill_id == skill.id))
            await db.delete(skill)
            await db.commit()
            await db.refresh(tool)

            # ON DELETE SET NULL: the tool survives but stops claiming a bundle,
            # so it can no longer take the sandbox path with a stale digest.
            assert tool.source_skill_id is None
        finally:
            await _cleanup(db)
