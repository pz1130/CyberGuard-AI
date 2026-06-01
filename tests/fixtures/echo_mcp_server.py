"""Minimal JSON-RPC echo 'MCP server' for tests: echoes params back as result."""
import sys
import json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
    except Exception:
        continue
    resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"echo": req.get("params", {})}}
    sys.stdout.write(json.dumps(resp) + "\n")
    sys.stdout.flush()
