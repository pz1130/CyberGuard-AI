"""run_python needs a run id to scope an approval by; today none arrives."""
from __future__ import annotations

import inspect

from app.services.internal_agent import InternalAgentRunner


def test_execute_accepts_a_run_request_id():
    sig = inspect.signature(InternalAgentRunner.execute)
    assert "run_request_id" in sig.parameters


def test_runner_reads_the_agent_code_execution_mode():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "a", "system_prompt": "p",
        "code_execution_mode": "auto", "metadata_json": {},
    })
    assert runner.code_execution_mode == "auto"


def test_mode_defaults_to_approval_when_the_config_omits_it():
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "a", "system_prompt": "p", "metadata_json": {},
    })
    assert runner.code_execution_mode == "approval"


def test_a_null_mode_column_still_means_approval():
    # An older row read before the migration backfilled would give None.
    runner = InternalAgentRunner({
        "id": 1, "agent_name": "a", "system_prompt": "p",
        "code_execution_mode": None, "metadata_json": {},
    })
    assert runner.code_execution_mode == "approval"


def test_executor_forwards_the_run_request_id():
    import app.services.agent_executor as ae
    src = inspect.getsource(ae)
    assert 'context or {}).get("request_id")' in src
    assert "run_request_id=" in src
