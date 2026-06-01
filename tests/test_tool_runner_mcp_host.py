import os
import sys
import unittest

from tool_runner import mcp_host

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "echo_mcp_server.py")


class TestMcpHost(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        # Clean up any spawned servers between tests.
        for name in list(mcp_host._live_processes):
            await mcp_host.stop_server(name)

    async def test_start_status_stop_lifecycle(self):
        ok = await mcp_host.start_server("sleeper", "/bin/sleep", ["30"], {})
        self.assertTrue(ok)
        self.assertTrue(mcp_host.is_running("sleeper"))
        await mcp_host.stop_server("sleeper")
        self.assertFalse(mcp_host.is_running("sleeper"))

    async def test_start_rejects_bad_command(self):
        ok = await mcp_host.start_server("bad", "relative/path", [], {})
        self.assertFalse(ok)
        self.assertFalse(mcp_host.is_running("bad"))

    async def test_rpc_echo_roundtrip(self):
        result = await mcp_host.rpc(
            name="echo",
            command=sys.executable,
            args=[_FIXTURE],
            env={},
            method="tools/call",
            params={"name": "x", "arguments": {"a": 1}},
            timeout=10,
        )
        self.assertEqual(result, {"echo": {"name": "x", "arguments": {"a": 1}}})

    async def test_rpc_autostarts_then_reuses(self):
        # First rpc auto-starts the server; it then stays live for the second.
        await mcp_host.rpc("echo2", sys.executable, [_FIXTURE], {},
                           "tools/list", {}, 10)
        self.assertTrue(mcp_host.is_running("echo2"))


if __name__ == "__main__":
    unittest.main()
