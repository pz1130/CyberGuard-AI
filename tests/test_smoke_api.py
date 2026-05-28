import asyncio
import json
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

import bcrypt
from sqlalchemy import select

from app.core.database import get_db_context
from app.models.user import User


BASE_URL = os.getenv("SMOKE_BASE_URL", "http://localhost:8000")
API_BASE = f"{BASE_URL}/api/v1"
SMOKE_USER = os.getenv("SMOKE_USER", "smoke_admin")
SMOKE_PASSWORD = os.getenv("SMOKE_PASSWORD", "smoke_admin_123")
SMOKE_EMAIL = os.getenv("SMOKE_EMAIL", "smoke_admin@local.test")


def _request(method: str, path: str, body: dict | None = None, token: str | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, (json.loads(raw) if raw else None)


async def _ensure_smoke_admin():
    hashed = bcrypt.hashpw(SMOKE_PASSWORD.encode(), bcrypt.gensalt()).decode()
    async with get_db_context() as session:
        result = await session.execute(select(User).where(User.username == SMOKE_USER))
        user = result.scalar_one_or_none()
        if user:
            user.hashed_password = hashed
            user.role = "admin"
            user.is_active = True
            user.email = SMOKE_EMAIL
        else:
            session.add(
                User(
                    username=SMOKE_USER,
                    email=SMOKE_EMAIL,
                    hashed_password=hashed,
                    role="admin",
                    full_name="Smoke Admin",
                    is_active=True,
                )
            )
        await session.commit()


class TestAPISmoke(unittest.TestCase):
    token: str

    @classmethod
    def setUpClass(cls):
        asyncio.run(_ensure_smoke_admin())
        code, data = _request(
            "POST",
            "/auth/login",
            {"username": SMOKE_USER, "password": SMOKE_PASSWORD},
        )
        if code != 200 or not data or "access_token" not in data:
            raise RuntimeError(f"Login failed in smoke setup: {code} {data}")
        cls.token = data["access_token"]

    def test_health(self):
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertEqual(payload.get("status"), "ok")

    def test_auth_me(self):
        code, data = _request("GET", "/auth/me", token=self.token)
        self.assertEqual(code, 200)
        self.assertEqual(data["username"], SMOKE_USER)

    def test_schedule_crud(self):
        name = f"smoke-schedule-{uuid.uuid4().hex[:8]}"
        code, created = _request(
            "POST",
            "/schedule",
            {
                "name": name,
                "description": "smoke test",
                "cron_expression": "*/10 * * * *",
                "task_type": "agent_execution",
                "task_config": {"kind": "smoke"},
                "is_active": True,
            },
            token=self.token,
        )
        self.assertEqual(code, 201)
        task_id = created["task_id"]

        code, listing = _request("GET", "/schedule", token=self.token)
        self.assertEqual(code, 200)
        self.assertIn("schedules", listing)
        self.assertTrue(any(item["task_id"] == task_id for item in listing["schedules"]))

        code, _ = _request("DELETE", f"/schedule/{task_id}", token=self.token)
        self.assertEqual(code, 204)

    def test_knowledge_base_crud(self):
        name = f"smoke-kb-{uuid.uuid4().hex[:8]}"
        code, created = _request(
            "POST",
            "/knowledge/bases",
            {
                "name": name,
                "description": "smoke kb",
                "embedding_model": "text-embedding-3-small",
                "rerank_model": "none",
                "chunk_size": 500,
                "chunk_overlap": 100,
                "is_active": True,
            },
            token=self.token,
        )
        self.assertEqual(code, 201)
        kb_id = created["id"]

        code, listing = _request("GET", "/knowledge/bases", token=self.token)
        self.assertEqual(code, 200)
        self.assertIn("knowledge_bases", listing)
        self.assertTrue(any(item["id"] == kb_id for item in listing["knowledge_bases"]))

        code, _ = _request("DELETE", f"/knowledge/bases/{kb_id}", token=self.token)
        self.assertEqual(code, 204)

    def test_mcp_server_crud(self):
        name = f"smoke-mcp-{uuid.uuid4().hex[:8]}"
        code, created = _request(
            "POST",
            "/mcp/servers",
            {
                "name": name,
                "transport_type": "streamable_http",
                "url": "https://example.com",
                "description": "smoke mcp",
                "is_active": False,
                "timeout": 10,
            },
            token=self.token,
        )
        self.assertEqual(code, 201)
        server_id = created["id"]

        code, listing = _request("GET", "/mcp/servers", token=self.token)
        self.assertEqual(code, 200)
        self.assertIn("servers", listing)
        self.assertTrue(any(item["id"] == server_id for item in listing["servers"]))

        code, _ = _request("DELETE", f"/mcp/servers/{server_id}", token=self.token)
        self.assertEqual(code, 204)

    def test_chat_submit_and_task_fetch(self):
        code, submitted = _request(
            "POST",
            "/chat",
            {"message": "smoke test task"},
            token=self.token,
        )
        self.assertEqual(code, 202)
        task_id = submitted["task_id"]

        code, task = _request("GET", f"/tasks/{task_id}", token=self.token)
        self.assertEqual(code, 200)
        self.assertEqual(task["execution_id"], task_id)

    def test_internal_agent_crud(self):
        """Create internal agent, verify kind=internal, reject invalid internal."""
        name = f"smoke-int-{uuid.uuid4().hex[:8]}"

        # Create internal agent (requires llm_provider_id — use placeholder that passes schema)
        code, created = _request(
            "POST",
            "/agents",
            {
                "agent_name": name,
                "kind": "internal",
                "llm_provider_id": 999,  # may not exist but passes validation
                "system_prompt": "You are a smoke test internal agent.",
                "permission_level": "medium",
            },
            token=self.token,
        )
        self.assertEqual(code, 201, msg=f"create internal failed: {created}")
        self.assertEqual(created.get("kind"), "internal")
        agent_id = created["id"]

        # List agents — should include the new one with kind=internal
        code, listing = _request("GET", "/agents", token=self.token)
        self.assertEqual(code, 200)
        found = next((a for a in listing.get("agents", []) if a["id"] == agent_id), None)
        self.assertIsNotNone(found, msg=f"agent {agent_id} not found in list")
        self.assertEqual(found["kind"], "internal")

        # Delete
        code, _ = _request("DELETE", f"/agents/{agent_id}", token=self.token)
        self.assertEqual(code, 204)

    def test_internal_agent_validation(self):
        """Reject internal agent without llm_provider_id."""
        name = f"smoke-bad-int-{uuid.uuid4().hex[:8]}"
        code, err = _request(
            "POST",
            "/agents",
            {"agent_name": name, "kind": "internal"},
            token=self.token,
        )
        self.assertEqual(code, 400)
        self.assertIn("llm_provider_id", str(err).lower())


if __name__ == "__main__":
    unittest.main()
