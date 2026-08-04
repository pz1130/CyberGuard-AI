"""Sidecar main loop — JSONL over stdin/stdout. Never binds a port."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import traceback
from typing import Any, Dict, Optional, TextIO

from apps.desktop.sidecar.capabilities import capabilities_for_tier
from apps.desktop.sidecar.mcp_manager import MCP
from apps.desktop.sidecar.mcp_stdio import STDIO_CLIENT
from apps.desktop.sidecar.mock_agent import MockAgentHost


async def STDIO_CLIENT_STOP(server_id: str) -> bool:
    return await STDIO_CLIENT.stop(server_id)
from apps.desktop.sidecar.paths import data_root, logs_dir
from apps.desktop.sidecar.process_group import REGISTRY
from apps.desktop.sidecar.rpc import (
    error_msg,
    event_msg,
    read_request,
    result_msg,
    write_message,
)
from apps.desktop.sidecar.sessions import SessionStore

logger = logging.getLogger("cyberguard.desktop.sidecar")


class SidecarServer:
    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.agent = MockAgentHost()
        self.sessions = SessionStore()
        self._lock = asyncio.Lock()

    def _write(self, payload: Dict[str, Any]) -> None:
        write_message(self.stdout, payload)

    async def handle(self, req: Dict[str, Any]) -> None:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        try:
            if method == "ping":
                from apps.desktop.sidecar.filevault import filevault_status
                from apps.desktop.sidecar.paths import tmp_dir, workspace_dir
                from apps.desktop.sidecar.policy import policy_for_tier
                from apps.desktop.sidecar.provider import load_provider_config
                from apps.desktop.sidecar.sandbox import sandbox_public_status
                from apps.desktop.sidecar.audit_chain import verify_chain
                from apps.desktop.sidecar.backup_exclude import public_status as backup_status
                from apps.desktop.sidecar.data_crypto import public_status as crypto_status
                from apps.desktop.sidecar.episodic import get_store
                from apps.desktop.sidecar.evidence import get_evidence_store
                from apps.desktop.sidecar.run_pause import list_paused
                from apps.desktop.sidecar.secrets_store import public_status as secrets_status
                from apps.desktop.sidecar.tcc import tcc_status
                from apps.desktop.sidecar.trust_gate import get_trust_gate

                root = data_root()
                self._write(
                    result_msg(
                        req_id,
                        {
                            "ok": True,
                            "role": "sidecar",
                            "m1": True,
                            "m2": True,
                            "m3": True,
                            "m4": True,
                            "m5": True,
                            "m7": True,
                            "data_root": str(root),
                            "provider": load_provider_config().public_status(),
                            "filevault": filevault_status(),
                            "sandbox": sandbox_public_status(),
                            "tcc": tcc_status(),
                            "secrets": secrets_status(),
                            "audit": verify_chain(),
                            "episodic": get_store().stats(),
                            "trust": get_trust_gate().public_status(),
                            "evidence_count": len(get_evidence_store().list(limit=500)),
                            "paused_runs": list_paused(limit=10),
                            "data_protection": {
                                **crypto_status(),
                                "backup": backup_status(),
                                "filevault": filevault_status(),
                            },
                            "policy_defaults": {
                                "readonly": policy_for_tier(
                                    "readonly",
                                    workspace_root=str(workspace_dir()),
                                    managed_tmp=str(tmp_dir()),
                                ).public_status(),
                                "full": policy_for_tier(
                                    "full",
                                    workspace_root=str(workspace_dir()),
                                    managed_tmp=str(tmp_dir()),
                                ).public_status(),
                            },
                        },
                    )
                )
                return

            if method == "session.capabilities":
                tier = str(params.get("tier") or "readonly")
                caps = capabilities_for_tier(tier)
                self._write(result_msg(req_id, caps.describe()))
                return

            if method == "host.read_text":
                tier = str(params.get("tier") or "readonly")
                path = str(params.get("path") or "")
                max_bytes = int(params.get("max_bytes") or 200_000)
                caps = capabilities_for_tier(tier)
                if caps.operations.read is None:
                    self._write(
                        error_msg(req_id, "forbidden", "no read operations")
                    )
                    return
                try:
                    text = await caps.operations.read.read_text(
                        path, max_bytes=max_bytes
                    )
                    self._write(
                        result_msg(
                            req_id,
                            {
                                "ok": True,
                                "path": path,
                                "text": text,
                                "real_read": caps.real_read,
                                "sandboxed": caps.real_read,
                            },
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "host_read", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "host.list_dir":
                tier = str(params.get("tier") or "readonly")
                path = str(params.get("path") or "")
                caps = capabilities_for_tier(tier)
                if caps.operations.read is None:
                    self._write(
                        error_msg(req_id, "forbidden", "no read operations")
                    )
                    return
                try:
                    entries = await caps.operations.read.list_dir(path)
                    self._write(
                        result_msg(
                            req_id,
                            {
                                "ok": True,
                                "path": path,
                                "entries": list(entries),
                                "real_read": caps.real_read,
                                "sandboxed": caps.real_read,
                            },
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "host_list", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "host.write_text":
                tier = str(params.get("tier") or "full")
                path = str(params.get("path") or "")
                content = str(
                    params.get("content") if params.get("content") is not None else ""
                )
                caps = capabilities_for_tier(tier)
                if caps.operations.edit is None:
                    self._write(
                        error_msg(req_id, "forbidden", "no edit operations on this tier")
                    )
                    return
                try:
                    await caps.operations.edit.write_text(path, content)
                    self._write(
                        result_msg(
                            req_id,
                            {
                                "ok": True,
                                "path": path,
                                "bytes": len(content.encode("utf-8")),
                                "real_edit": caps.real_edit,
                                "sandboxed": caps.real_edit,
                            },
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "host_write", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "host.delete":
                tier = str(params.get("tier") or "full")
                path = str(params.get("path") or "")
                caps = capabilities_for_tier(tier)
                if caps.operations.edit is None:
                    self._write(
                        error_msg(req_id, "forbidden", "no edit operations on this tier")
                    )
                    return
                try:
                    await caps.operations.edit.delete(path)
                    self._write(
                        result_msg(
                            req_id,
                            {
                                "ok": True,
                                "path": path,
                                "real_edit": caps.real_edit,
                                "sandboxed": caps.real_edit,
                            },
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "host_delete", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "host.run":
                tier = str(params.get("tier") or "full")
                argv = params.get("argv")
                timeout = int(params.get("timeout_seconds") or 30)
                cwd = params.get("cwd")
                caps = capabilities_for_tier(tier)
                if caps.operations.exec is None:
                    self._write(
                        error_msg(req_id, "forbidden", "no exec operations on this tier")
                    )
                    return
                if not isinstance(argv, list):
                    self._write(
                        error_msg(req_id, "bad_params", "argv must be an array of strings")
                    )
                    return
                try:
                    result = await caps.operations.exec.run(
                        [str(x) for x in argv],
                        timeout_seconds=timeout,
                        cwd=str(cwd) if cwd else None,
                    )
                    self._write(
                        result_msg(
                            req_id,
                            {
                                "ok": True,
                                "result": result,
                                "real_exec": caps.real_exec,
                                "sandboxed": bool(result.get("sandboxed")),
                            },
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "host_run", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "sessions.create":
                title = str(params.get("title") or "Untitled")
                tier = str(params.get("tier") or "readonly")
                meta = self.sessions.create(title=title, tier=tier)
                self._write(
                    result_msg(
                        req_id,
                        {
                            "session_id": meta.session_id,
                            "title": meta.title,
                            "tier": meta.tier,
                            "created_at": meta.created_at,
                        },
                    )
                )
                return

            if method == "sessions.list":
                rows = [
                    {
                        "session_id": m.session_id,
                        "title": m.title,
                        "tier": m.tier,
                        "updated_at": m.updated_at,
                        "event_count": m.event_count,
                    }
                    for m in self.sessions.list()
                ]
                self._write(result_msg(req_id, {"sessions": rows}))
                return

            if method == "sessions.events":
                sid = str(params.get("session_id") or "")
                try:
                    events = list(self.sessions.iter_events(sid))
                except Exception as exc:  # noqa: BLE001
                    from apps.desktop.sidecar.sessions import SessionShreddedError

                    if isinstance(exc, SessionShreddedError):
                        self._write(
                            error_msg(
                                req_id,
                                "shredded",
                                f"session body unrecoverable: {exc}",
                            )
                        )
                        return
                    raise
                self._write(result_msg(req_id, {"session_id": sid, "events": events}))
                return

            if method == "sessions.delete":
                sid = str(params.get("session_id") or "")
                if not sid:
                    self._write(error_msg(req_id, "bad_params", "session_id required"))
                    return
                crypto_shred = params.get("crypto_shred")
                if crypto_shred is None:
                    crypto_shred = True
                result = self.sessions.delete(sid, crypto_shred=bool(crypto_shred))
                try:
                    from apps.desktop.sidecar.audit_chain import append_event

                    append_event(
                        "session_delete",
                        {
                            "session_id": sid,
                            "crypto_shred": bool(crypto_shred),
                            "body_unrecoverable": result.get("body_unrecoverable"),
                        },
                        approval_type="self",
                        session_id=sid,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("audit session_delete failed", exc_info=True)
                self._write(result_msg(req_id, result))
                return

            if method == "sessions.purge_expired":
                days = params.get("retention_days")
                result = self.sessions.purge_expired(
                    retention_days=int(days) if days is not None else None
                )
                self._write(result_msg(req_id, result))
                return

            if method == "data_protection.status":
                from apps.desktop.sidecar.backup_exclude import (
                    apply_exclusions,
                    public_status as backup_status,
                )
                from apps.desktop.sidecar.data_crypto import public_status as crypto_status
                from apps.desktop.sidecar.filevault import filevault_status

                reapply = bool(params.get("reapply_exclusions"))
                applied = apply_exclusions() if reapply else None
                self._write(
                    result_msg(
                        req_id,
                        {
                            "crypto": crypto_status(),
                            "backup": backup_status(),
                            "filevault": filevault_status(),
                            "applied": applied,
                        },
                    )
                )
                return

            if method == "skills.list":
                from apps.desktop.sidecar.skill_loader import list_skills

                rows = [
                    {
                        "name": s.name,
                        "description": s.description,
                        "version": s.version,
                        "source": s.source,
                        "mode": s.mode,
                        "requires_tools": s.requires_tools,
                        "sha256": s.sha256[:16],
                    }
                    for s in list_skills(include_body=False)
                ]
                self._write(result_msg(req_id, {"skills": rows}))
                return

            if method == "skills.load":
                from apps.desktop.sidecar.skill_loader import load_skill_for_tool

                name = str(params.get("name") or "")
                result = load_skill_for_tool(name)
                self._write(result_msg(req_id, result))
                return

            if method == "plan.list":
                from apps.desktop.sidecar.plan_mode import get_plan_store

                self._write(
                    result_msg(req_id, {"plans": get_plan_store().list()})
                )
                return

            if method == "plan.get":
                from apps.desktop.sidecar.plan_mode import get_plan_store

                pid = str(params.get("plan_id") or "")
                req = get_plan_store().get(pid)
                if not req:
                    self._write(error_msg(req_id, "not_found", "unknown plan_id"))
                    return
                self._write(result_msg(req_id, req.public_dict()))
                return

            if method == "plan.approve":
                from apps.desktop.sidecar.plan_mode import get_plan_store

                pid = str(params.get("plan_id") or "")
                revised = params.get("revised_plan")
                revised_s = str(revised) if revised is not None else None
                out = get_plan_store().decide(
                    pid, approve=True, revised_plan=revised_s
                )
                if not out.get("ok"):
                    self._write(
                        error_msg(
                            req_id,
                            str(out.get("error") or "plan"),
                            str(out.get("message") or out.get("error") or "failed"),
                        )
                    )
                    return
                self._write(result_msg(req_id, out))
                return

            if method == "plan.reject":
                from apps.desktop.sidecar.plan_mode import get_plan_store

                pid = str(params.get("plan_id") or "")
                reason = str(params.get("reason") or "rejected_by_user")
                out = get_plan_store().decide(pid, approve=False, reason=reason)
                if not out.get("ok"):
                    self._write(
                        error_msg(
                            req_id,
                            str(out.get("error") or "plan"),
                            str(out.get("error") or "failed"),
                        )
                    )
                    return
                self._write(result_msg(req_id, out))
                return

            if method == "policy_events.tail":
                from apps.desktop.sidecar.policy_events import tail_policy_events

                n = int(params.get("n") or 50)
                self._write(result_msg(req_id, {"events": tail_policy_events(n)}))
                return

            if method == "provider.get":
                from apps.desktop.sidecar.provider import get_provider_public

                self._write(result_msg(req_id, get_provider_public()))
                return

            if method == "provider.set":
                from apps.desktop.sidecar.provider import set_provider_config

                try:
                    out = set_provider_config(params if isinstance(params, dict) else {})
                    self._write(result_msg(req_id, out))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "provider", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "provider.test":
                from apps.desktop.sidecar.provider import test_provider_connection

                try:
                    out = await test_provider_connection()
                    self._write(result_msg(req_id, out))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "provider", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "ui.prefs.get":
                from apps.desktop.sidecar.ui_prefs import get_prefs

                self._write(result_msg(req_id, get_prefs()))
                return

            if method == "ui.prefs.set":
                from apps.desktop.sidecar.ui_prefs import set_prefs

                try:
                    out = set_prefs(params if isinstance(params, dict) else {})
                    self._write(result_msg(req_id, out))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "ui.prefs", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "mcp.config.list":
                from apps.desktop.sidecar.mcp_config import list_mcp_config_public

                self._write(result_msg(req_id, list_mcp_config_public()))
                return

            if method == "mcp.config.upsert":
                from apps.desktop.sidecar.mcp_config import upsert_mcp_server

                try:
                    out = upsert_mcp_server(params if isinstance(params, dict) else {})
                    self._write(result_msg(req_id, out))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "mcp.config", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "mcp.config.delete":
                from apps.desktop.sidecar.mcp_config import delete_mcp_server

                try:
                    out = delete_mcp_server(str(params.get("id") or params.get("server_id") or ""))
                    self._write(result_msg(req_id, out))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "mcp.config", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "mcp.list":
                self._write(
                    result_msg(
                        req_id,
                        {
                            "running": MCP.list(),
                            "configured": MCP.configured_servers(),
                        },
                    )
                )
                return

            if method == "mcp.discover":
                tier = str(params.get("tier") or "readonly")
                tools, routing = await MCP.discover_tools_for_agent(tier=tier)
                self._write(
                    result_msg(
                        req_id,
                        {
                            "tools": [
                                {
                                    "name": t["function"]["name"],
                                    "description": t["function"].get("description"),
                                }
                                for t in tools
                            ],
                            "servers": list({r[0].id for r in routing.values()}),
                        },
                    )
                )
                return

            if method == "mcp.call":
                # Direct call for debugging: exposed name + arguments
                tools, routing = await MCP.discover_tools_for_agent(
                    tier=str(params.get("tier") or "readonly")
                )
                name = str(params.get("name") or "")
                args = params.get("arguments") or {}
                result = await MCP.call_routed(routing, name, args)
                self._write(result_msg(req_id, {"result": result}))
                return

            if method == "mcp.spawn_mock":
                server_id = str(params.get("server_id") or "mock-1")
                hold = float(params.get("hold_seconds") or 3600)
                info = MCP.spawn_mock(server_id, hold_seconds=hold)
                self._write(result_msg(req_id, info))
                return

            if method == "mcp.stop":
                server_id = str(params.get("server_id") or "")
                ok = MCP.stop(server_id)
                if not ok:
                    ok = await STDIO_CLIENT_STOP(server_id)
                self._write(result_msg(req_id, {"ok": ok, "server_id": server_id}))
                return

            if method == "secrets.status":
                from apps.desktop.sidecar.secrets_store import public_status

                self._write(result_msg(req_id, public_status()))
                return

            if method == "secrets.set_provider_key":
                from apps.desktop.sidecar.secrets_store import set_provider_api_key

                key = str(params.get("api_key") or "")
                if not key:
                    self._write(error_msg(req_id, "bad_params", "api_key required"))
                    return
                try:
                    set_provider_api_key(key)
                    # never echo key
                    self._write(result_msg(req_id, {"ok": True, "slot": "provider/default"}))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "secrets", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "secrets.delete_provider_key":
                from apps.desktop.sidecar.secrets_store import (
                    SERVICE_PROVIDER,
                    delete_secret,
                )

                ok = delete_secret(SERVICE_PROVIDER, "default")
                self._write(result_msg(req_id, {"ok": ok}))
                return

            if method == "secrets.set_mcp":
                from apps.desktop.sidecar.secrets_store import set_mcp_secret

                server_id = str(params.get("server_id") or "")
                secret = str(params.get("secret") or "")
                if not server_id or not secret:
                    self._write(
                        error_msg(req_id, "bad_params", "server_id and secret required")
                    )
                    return
                try:
                    set_mcp_secret(server_id, secret)
                    self._write(
                        result_msg(
                            req_id,
                            {"ok": True, "slot": f"mcp/{server_id}"},
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "secrets", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "secrets.migrate_provider_json":
                # Move api_key from provider.json into secrets store; strip file key
                from apps.desktop.sidecar.paths import data_root as dr
                from apps.desktop.sidecar.secrets_store import set_provider_api_key

                path = dr() / "provider.json"
                if not path.is_file():
                    self._write(
                        result_msg(req_id, {"ok": False, "reason": "no_provider_json"})
                    )
                    return
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "secrets", f"read_failed:{type(exc).__name__}")
                    )
                    return
                key = str((data or {}).get("api_key") or "")
                if not key:
                    self._write(
                        result_msg(req_id, {"ok": False, "reason": "no_api_key_in_file"})
                    )
                    return
                set_provider_api_key(key)
                data["api_key"] = ""
                data["api_key_in_keychain"] = True
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                try:
                    import os as _os

                    _os.chmod(path, 0o600)
                except OSError:
                    pass
                self._write(
                    result_msg(
                        req_id,
                        {"ok": True, "migrated": True, "provider_json_key_cleared": True},
                    )
                )
                return

            if method == "audit.verify":
                from apps.desktop.sidecar.audit_chain import verify_chain

                self._write(result_msg(req_id, verify_chain()))
                return

            if method == "audit.tail":
                from apps.desktop.sidecar.audit_chain import tail

                n = int(params.get("n") or 20)
                self._write(result_msg(req_id, {"events": tail(n)}))
                return

            if method == "episodic.stats":
                from apps.desktop.sidecar.episodic import get_store

                self._write(result_msg(req_id, get_store().stats()))
                return

            if method == "episodic.recall":
                from apps.desktop.sidecar.episodic import get_store

                task = str(params.get("task") or "")
                top_k = int(params.get("top_k") or 3)
                success_only = params.get("success_only")
                if success_only is None:
                    success_only = True
                eps = get_store().recall(
                    task=task,
                    top_k=top_k,
                    success_only=bool(success_only),
                )
                self._write(
                    result_msg(
                        req_id,
                        {
                            "episodes": [
                                e.public_dict(strip_hostile_outcome=True) for e in eps
                            ],
                            "upload_enabled": False,
                        },
                    )
                )
                return

            if method == "episodic.record":
                from apps.desktop.sidecar.episodic import get_store

                task = str(params.get("task") or "")
                if not task:
                    self._write(error_msg(req_id, "bad_params", "task required"))
                    return
                eid = get_store().record(
                    task=task,
                    approach=str(params.get("approach") or ""),
                    outcome=str(params.get("outcome") or ""),
                    success=bool(params.get("success", True)),
                    tool_count=int(params.get("tool_count") or 0),
                    source_trust=str(params.get("source_trust") or "trusted"),
                    agent_scope=str(params.get("agent_scope") or "desktop"),
                    duration_ms=params.get("duration_ms"),
                )
                self._write(
                    result_msg(
                        req_id,
                        {"ok": eid is not None, "id": eid, "upload_enabled": False},
                    )
                )
                return

            if method == "trust.status":
                from apps.desktop.sidecar.trust_gate import get_trust_gate

                gate = get_trust_gate()
                self._write(
                    result_msg(
                        req_id,
                        {**gate.public_status(), "decisions_list": gate.list_decisions()},
                    )
                )
                return

            if method == "trust.evaluate":
                from apps.desktop.sidecar.trust_gate import get_trust_gate

                path = str(params.get("path") or "")
                if not path:
                    self._write(error_msg(req_id, "bad_params", "path required"))
                    return
                d = get_trust_gate().evaluate(path, purpose=str(params.get("purpose") or "load"))
                self._write(
                    result_msg(
                        req_id,
                        {
                            "path": d.path,
                            "level": d.level,
                            "decision": d.decision,
                            "reason": d.reason,
                            "source": d.source,
                        },
                    )
                )
                return

            if method == "trust.set":
                from apps.desktop.sidecar.trust_gate import get_trust_gate

                path = str(params.get("path") or "")
                level = str(params.get("level") or "")
                if not path or level not in ("trusted", "untrusted", "ask"):
                    self._write(
                        error_msg(
                            req_id,
                            "bad_params",
                            "path and level=trusted|untrusted|ask required",
                        )
                    )
                    return
                try:
                    out = get_trust_gate().set_trust(
                        path, level, note=str(params.get("note") or "")  # type: ignore[arg-type]
                    )
                    self._write(result_msg(req_id, {"ok": True, **out}))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "trust", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "evidence.list":
                from apps.desktop.sidecar.evidence import get_evidence_store

                self._write(
                    result_msg(
                        req_id,
                        {"evidence": get_evidence_store().list(int(params.get("limit") or 100))},
                    )
                )
                return

            if method == "evidence.register":
                from apps.desktop.sidecar.evidence import get_evidence_store

                path = str(params.get("path") or "")
                if not path:
                    self._write(error_msg(req_id, "bad_params", "path required"))
                    return
                try:
                    item = get_evidence_store().register(
                        path, note=str(params.get("note") or "")
                    )
                    self._write(result_msg(req_id, {"ok": True, "item": item}))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "evidence", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "evidence.verify":
                from apps.desktop.sidecar.evidence import get_evidence_store

                eid = str(params.get("evidence_id") or "")
                self._write(result_msg(req_id, get_evidence_store().verify(eid)))
                return

            if method == "runs.paused":
                from apps.desktop.sidecar.run_pause import list_paused

                self._write(result_msg(req_id, {"paused": list_paused()}))
                return

            if method == "export.encrypted":
                from apps.desktop.sidecar.export_bundle import export_encrypted

                dest = str(params.get("dest_path") or "")
                if not dest:
                    self._write(error_msg(req_id, "bad_params", "dest_path required"))
                    return
                passphrase = params.get("passphrase")
                recipient = params.get("age_recipient")
                include = params.get("include")
                try:
                    out = export_encrypted(
                        dest,
                        passphrase=str(passphrase) if passphrase else None,
                        age_recipient=str(recipient) if recipient else None,
                        include=include if isinstance(include, list) else None,
                    )
                    self._write(result_msg(req_id, out))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "export", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "uninstall.inventory":
                from apps.desktop.sidecar.uninstall import inventory

                self._write(result_msg(req_id, inventory()))
                return

            if method == "uninstall.execute":
                from apps.desktop.sidecar.uninstall import execute

                confirm = bool(params.get("confirm"))
                dry_run = params.get("dry_run")
                if dry_run is None:
                    dry_run = True
                out = execute(confirm=confirm, dry_run=bool(dry_run))
                self._write(result_msg(req_id, out))
                return

            if method == "update.verify":
                from apps.desktop.sidecar.update_verify import (
                    UpdateVerifyError,
                    verify_update,
                )

                manifest = params.get("manifest")
                if not isinstance(manifest, dict):
                    self._write(error_msg(req_id, "bad_params", "manifest object required"))
                    return
                current = str(params.get("current_version") or "0.1.0-m1")
                artifact_b64 = params.get("artifact_b64")
                artifact = None
                if artifact_b64:
                    import base64

                    artifact = base64.b64decode(str(artifact_b64))
                try:
                    out = verify_update(
                        manifest, current_version=current, artifact_bytes=artifact
                    )
                    self._write(result_msg(req_id, out))
                except UpdateVerifyError as exc:
                    self._write(error_msg(req_id, "update_rejected", str(exc)))
                except Exception as exc:  # noqa: BLE001
                    self._write(
                        error_msg(req_id, "update", f"{type(exc).__name__}: {exc}")
                    )
                return

            if method == "agent.abort":
                run_id = str(params.get("run_id") or "")
                ok = self.agent.abort(run_id)
                self._write(result_msg(req_id, {"ok": ok, "run_id": run_id}))
                return

            if method == "agent.steer":
                run_id = str(params.get("run_id") or "")
                message = str(params.get("message") or "")
                ok = self.agent.steer(run_id, message)
                self._write(result_msg(req_id, {"ok": ok, "run_id": run_id}))
                return

            if method == "agent.resume":
                run_id = str(params.get("run_id") or "")
                if not run_id:
                    self._write(error_msg(req_id, "bad_params", "run_id required"))
                    return
                session_id = params.get("session_id")
                if not session_id:
                    meta = self.sessions.create(title=f"resume {run_id[:8]}", tier="readonly")
                    session_id = meta.session_id
                else:
                    session_id = str(session_id)
                async for ev in self.agent.resume(run_id):
                    ev = dict(ev)
                    ev["session_id"] = session_id
                    self.sessions.append_event(session_id, ev)
                    self._write(event_msg(req_id, ev))
                self._write(
                    result_msg(
                        req_id, {"ok": True, "done": True, "session_id": session_id}
                    )
                )
                return

            if method == "agent.run":
                task = str(params.get("task") or "")
                if not task:
                    self._write(error_msg(req_id, "bad_params", "task required"))
                    return
                tier = str(params.get("tier") or "readonly")
                system_prompt = params.get("system_prompt")
                session_id = params.get("session_id")
                if not session_id:
                    meta = self.sessions.create(
                        title=(task[:48] + "…") if len(task) > 48 else task,
                        tier=tier,
                    )
                    session_id = meta.session_id
                else:
                    session_id = str(session_id)

                # Stream user_task so UI can confirm the exact text that ran
                user_ev = {
                    "type": "user_task",
                    "task": task,
                    "tier": tier,
                    "session_id": session_id,
                }
                self.sessions.append_event(session_id, user_ev)
                self._write(event_msg(req_id, user_ev))
                try:
                    from apps.desktop.sidecar.audit_chain import append_event

                    append_event(
                        "user_task",
                        {"task": task[:500], "tier": tier},
                        approval_type="self",
                        session_id=session_id,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("audit append user_task failed", exc_info=True)

                run_id_seen: Optional[str] = None
                async for ev in self.agent.run(
                    task=task,
                    tier=tier,
                    system_prompt=system_prompt,
                ):
                    ev = dict(ev)
                    ev["session_id"] = session_id
                    self.sessions.append_event(session_id, ev)
                    self._write(event_msg(req_id, ev))
                    et = str(ev.get("type") or "")
                    if et == "run_started":
                        run_id_seen = str(ev.get("run_id") or "") or None
                    if et in (
                        "run_started",
                        "tool_call_end",
                        "answer_ready",
                        "error",
                        "plan_ready",
                        "plan_approved",
                        "plan_rejected",
                    ):
                        try:
                            from apps.desktop.sidecar.audit_chain import append_event

                            payload: Dict[str, Any] = {"type": et}
                            if et == "tool_call_end":
                                payload["name"] = ev.get("name")
                                payload["error"] = bool(ev.get("error"))
                            if et == "run_started":
                                payload["tier"] = ev.get("tier")
                                payload["plan_required"] = ev.get("plan_required")
                                prov = ev.get("provider") or {}
                                if isinstance(prov, dict):
                                    payload["provider_mode"] = prov.get("mode")
                            if et in ("plan_ready", "plan_approved", "plan_rejected"):
                                payload["plan_id"] = ev.get("plan_id")
                                payload["status"] = ev.get("status")
                                payload["approval_type"] = ev.get("approval_type") or "self"
                                if et == "plan_approved" and ev.get("plan_summary"):
                                    payload["plan_summary"] = str(ev.get("plan_summary"))[:1500]
                            at = str(ev.get("approval_type") or "self")
                            append_event(
                                et,
                                payload,
                                approval_type=at if at in ("self", "segregation", "none") else "self",
                                session_id=session_id,
                                run_id=run_id_seen or str(ev.get("run_id") or "") or None,
                            )
                        except Exception:  # noqa: BLE001
                            logger.debug("audit append %s failed", et, exc_info=True)
                self._write(
                    result_msg(
                        req_id,
                        {"ok": True, "done": True, "session_id": session_id},
                    )
                )
                return

            self._write(error_msg(req_id, "unknown_method", f"unknown method: {method}"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("request failed")
            self._write(
                error_msg(req_id, "internal", f"{type(exc).__name__}: {exc}")
            )

    async def run_forever(self) -> None:
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, self.stdin.readline)
            if line == "":
                break
            try:
                req = read_request(line)
            except Exception as exc:  # noqa: BLE001
                self._write(error_msg(None, "parse_error", str(exc)))
                continue
            if req is None:
                continue
            await self.handle(req)


def _install_signals() -> None:
    _shutting_down = {"v": False}

    def _shutdown(signum, _frame) -> None:
        if _shutting_down["v"]:
            return
        _shutting_down["v"] = True
        try:
            logger.info("signal %s — cleanup children", signum)
            MCP.stop_all()
            REGISTRY.kill_all(sig=signal.SIGTERM)
        except Exception:
            pass
        os._exit(0)

    import os

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except Exception:
            pass


def main() -> None:
    logs_dir()
    # M3: mark sensitive dirs for backup exclusion (idempotent)
    try:
        from apps.desktop.sidecar.backup_exclude import apply_exclusions

        apply_exclusions()
    except Exception:  # noqa: BLE001
        pass
    # Ensure index encryption key exists when encryption is on
    try:
        from apps.desktop.sidecar.data_crypto import ensure_index_key, encryption_enabled

        if encryption_enabled():
            ensure_index_key()
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Orphan governance layers ① + ②
    REGISTRY.become_session_leader()
    REGISTRY.install_atexit()
    REGISTRY.start_watchdog(interval_sec=2.0)
    _install_signals()

    print(
        f"cyberguard-desktop-sidecar m1 mock (jsonl; no ports; data={data_root()})",
        file=sys.stderr,
        flush=True,
    )
    server = SidecarServer(sys.stdin, sys.stdout)
    try:
        asyncio.run(server.run_forever())
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            asyncio.run(MCP.stop_all_async())
        except Exception:
            MCP.stop_all()
        REGISTRY.kill_all()
        REGISTRY.stop_watchdog()


if __name__ == "__main__":
    main()
