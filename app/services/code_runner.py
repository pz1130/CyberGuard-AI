"""Run model-authored code in the no-network sandbox.

The sandbox already takes ``files`` plus ``argv``, so a model-authored program
is just a bundle with one file in it — no runner change was needed for this.

Deliberately imports ``SKILL_RUNNER_URL`` and never ``SKILL_RUNNER_NET_URL``:
the egress allowlist exists for scripts a human reviewed and named hosts for,
and code written seconds ago by a model has neither. INV-42 asserts this.
"""
from __future__ import annotations

import base64
from typing import Any, Dict

from app.services.tool_executor import SKILL_RUNNER_URL, _post_to_runner

ENTRYPOINT = "main.py"
DEFAULT_TIMEOUT_SECONDS = 30


async def run_code(code: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
    """Execute *code* as main.py in the sandbox. No network, no secrets."""
    payload = {
        "argv": ["python3", ENTRYPOINT],
        "timeout": int(timeout),
        "files": [{
            "path": ENTRYPOINT,
            "content_b64": base64.b64encode((code or "").encode("utf-8")).decode(),
        }],
    }
    return await _post_to_runner(SKILL_RUNNER_URL, payload, int(timeout))
