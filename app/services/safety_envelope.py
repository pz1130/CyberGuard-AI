"""Safety Envelope: pre-validation, rollback registry, revert + paging (B6)."""
from __future__ import annotations
import json
from datetime import timedelta
import httpx
from app.core.time import utc_now
from app.services.tool_executor import build_argv, TOOL_RUNNER_URL, RUNNER_TOKEN

ENVELOPE_CATEGORIES = {"contain_soft", "contain_hard", "remediate"}


def requires_envelope(category: str | None) -> bool:
    return (category or "").lower() in ENVELOPE_CATEGORIES


def has_rollback(tool) -> bool:
    return bool(getattr(tool, "rollback_command_template", None))


def _schema(tool) -> dict:
    try:
        return json.loads(tool.input_schema_json) if tool.input_schema_json else {}
    except json.JSONDecodeError:
        return {}


async def run_command(template: str, tool, args: dict, timeout: int = 60) -> dict:
    """Run a command template (validation/verification/rollback) in the tool-runner."""
    argv = build_argv(template, _schema(tool), args)
    async with httpx.AsyncClient(timeout=timeout + 10) as client:
        r = await client.post(f"{TOOL_RUNNER_URL}/run",
                              json={"argv": argv, "timeout": timeout},
                              headers={"X-Runner-Token": RUNNER_TOKEN})
    return r.json() if r.status_code == 200 else {"exit_code": -1, "stderr": r.text[:200]}


async def register_rollback(action_id: str, tool, args: dict, ttl_seconds: int = 3600) -> None:
    argv = build_argv(tool.rollback_command_template, _schema(tool), args)
    await _save_registration({
        "action_id": action_id,
        "tool_id": getattr(tool, "id", None),
        "tool_name": getattr(tool, "name", None),
        "rollback_argv": argv,
        "status": "registered",
        "created_at": utc_now(),
        "expires_at": utc_now() + timedelta(seconds=ttl_seconds),
    })


async def execute_rollback(action_id: str) -> bool:
    reg = await _load_registration(action_id)
    if reg is None or reg.status != "registered":
        return False
    async with httpx.AsyncClient(timeout=70) as client:
        try:
            r = await client.post(f"{TOOL_RUNNER_URL}/run",
                                  json={"argv": reg.rollback_argv, "timeout": 60},
                                  headers={"X-Runner-Token": RUNNER_TOKEN})
            result = r.json() if r.status_code == 200 else {"exit_code": -1, "stderr": r.text[:200]}
        except Exception as e:
            result = {"exit_code": -1, "stderr": str(e)}
    if result.get("exit_code") == 0:
        await _mark(action_id, "reverted", None)
        return True
    await _mark(action_id, "failed", str(result.get("stderr"))[:500])
    await _page_oncall(action_id, reg.tool_name, result.get("stderr"))
    return False


async def _save_registration(reg: dict) -> None:
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    async with get_db_context() as s:
        s.add(RollbackRegistration(**reg))
        await s.commit()


async def _load_registration(action_id: str):
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    from sqlalchemy import select
    async with get_db_context() as s:
        return (await s.execute(select(RollbackRegistration).where(
            RollbackRegistration.action_id == action_id))).scalar_one_or_none()


async def _mark(action_id: str, status: str, detail: str | None) -> None:
    from app.core.database import get_db_context
    from app.models.rollback import RollbackRegistration
    from sqlalchemy import select
    async with get_db_context() as s:
        reg = (await s.execute(select(RollbackRegistration).where(
            RollbackRegistration.action_id == action_id))).scalar_one_or_none()
        if reg:
            reg.status = status
            reg.detail = detail
            if status == "reverted":
                reg.reverted_at = utc_now()
            await s.commit()


async def _page_oncall(action_id: str, tool_name: str | None, stderr) -> None:
    import logging
    logging.getLogger("safety_envelope").error(
        "ROLLBACK FAILED action=%s tool=%s err=%s", action_id, tool_name, str(stderr)[:300])
