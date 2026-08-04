import os
import sys
import unittest

os.environ["RUNNER_TOKEN"] = "test-token"  # must be set BEFORE importing tool_runner.main
from fastapi.testclient import TestClient
from tool_runner.main import app
from tool_runner import mcp_host

_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "echo_mcp_server.py")
_HDR = {"X-Runner-Token": "test-token"}


class TestToolRunnerMcpEndpoints(unittest.TestCase):
    def setUp(self):
        # Use a context-managed TestClient so the BlockingPortal (event loop) is
        # shared across requests; otherwise each .post() creates a fresh loop
        # in a fresh thread and any subprocess created in one request can't be
        # awaited (proc.wait()) from another.
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        try:
            self.client.post("/mcp/stop", json={"name": "ep"}, headers=_HDR)
            self.client.post("/mcp/stop", json={"name": "epc"}, headers=_HDR)
        finally:
            self._client_ctx.__exit__(None, None, None)

    def test_requires_token(self):
        r = self.client.post("/mcp/start", json={"name": "ep", "command": "/bin/sleep",
                                                 "args": ["30"], "env": {}})
        self.assertEqual(r.status_code, 401)

    def test_start_status_stop(self):
        r = self.client.post("/mcp/start",
                             json={"name": "ep", "command": "/bin/sleep", "args": ["30"], "env": {}},
                             headers=_HDR)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["running"])

        r = self.client.post("/mcp/status", json={"name": "ep"}, headers=_HDR)
        self.assertTrue(r.json()["running"])

        r = self.client.post("/mcp/stop", json={"name": "ep"}, headers=_HDR)
        self.assertEqual(r.status_code, 200)

        r = self.client.post("/mcp/status", json={"name": "ep"}, headers=_HDR)
        self.assertFalse(r.json()["running"])

    def test_rpc_echo(self):
        r = self.client.post("/mcp/rpc", headers=_HDR, json={
            "name": "epc", "command": sys.executable, "args": [_FIXTURE], "env": {},
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"a": 1}},
            "timeout": 10,
        })
        self.assertEqual(r.status_code, 200, r.text)
        result = r.json()["result"]
        self.assertFalse(result.get("isError"))
        text = result["content"][0]["text"].replace(" ", "")
        self.assertIn('"a":1', text)

    def test_rpc_failure_returns_500(self):
        r = self.client.post("/mcp/rpc", headers=_HDR, json={
            "name": "nope", "command": "relative/bad", "args": [], "env": {},
            "method": "tools/call", "params": {}, "timeout": 5,
        })
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
