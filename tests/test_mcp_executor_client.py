import os
import types
import unittest
from unittest.mock import AsyncMock, patch

# Must be set BEFORE importing app.* so Settings() validation passes.
os.environ.setdefault(
    "ENCRYPTION_KEY",
    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
)
os.environ.setdefault(
    "SECRET_KEY",
    "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
)

import app.services.mcp_executor as mx


def _stdio_server(name="s1"):
    return types.SimpleNamespace(
        name=name, transport_type="stdio", command="/usr/bin/tool",
        args=["--flag"], env_vars_encrypted=None, timeout_seconds=15,
    )


class TestMcpExecutorClient(unittest.IsolatedAsyncioTestCase):
    async def test_start_proxies_and_returns_running(self):
        with patch.object(mx, "_runner_post", AsyncMock(return_value={"running": True})) as rp:
            ok = await mx._start_stdio_server(_stdio_server())
        self.assertTrue(ok)
        path, payload = rp.await_args.args
        self.assertEqual(path, "/mcp/start")
        self.assertEqual(payload["name"], "s1")
        self.assertEqual(payload["command"], "/usr/bin/tool")
        self.assertEqual(payload["args"], ["--flag"])
        self.assertEqual(payload["env"], {})

    async def test_stdio_status_proxies(self):
        with patch.object(mx, "_runner_post", AsyncMock(return_value={"running": False})):
            self.assertFalse(await mx.stdio_status("s1"))

    async def test_execute_stdio_tool_uses_rpc_tools_call(self):
        with patch.object(mx, "_runner_post", AsyncMock(return_value={"result": {"ok": 1}})) as rp:
            out = await mx.execute_stdio_tool(_stdio_server(), "mytool", {"x": 2})
        self.assertEqual(out, {"ok": 1})
        path, payload = rp.await_args.args
        self.assertEqual(path, "/mcp/rpc")
        self.assertEqual(payload["method"], "tools/call")
        self.assertEqual(payload["params"], {"name": "mytool", "arguments": {"x": 2}})
        self.assertEqual(payload["timeout"], 15)

    async def test_discover_stdio_tools_parses_list(self):
        with patch.object(mx, "_runner_post",
                          AsyncMock(return_value={"result": {"tools": [{"name": "t"}]}})):
            tools = await mx.discover_stdio_tools(_stdio_server())
        self.assertEqual(tools, [{"name": "t"}])

    async def test_execute_mcp_tool_dispatches_stdio_to_proxy(self):
        with patch.object(mx, "execute_stdio_tool", AsyncMock(return_value="X")) as st, \
             patch.object(mx, "execute_http_tool", AsyncMock()) as ht:
            out = await mx.execute_mcp_tool(_stdio_server(), "t", {})
        self.assertEqual(out, "X")
        st.assert_awaited_once()
        ht.assert_not_awaited()

    async def test_execute_mcp_tool_dispatches_http_locally(self):
        http_server = types.SimpleNamespace(transport_type="http")
        with patch.object(mx, "execute_stdio_tool", AsyncMock()) as st, \
             patch.object(mx, "execute_http_tool", AsyncMock(return_value="H")) as ht:
            out = await mx.execute_mcp_tool(http_server, "t", {})
        self.assertEqual(out, "H")
        ht.assert_awaited_once()
        st.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
