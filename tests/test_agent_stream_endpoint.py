import pytest
from types import SimpleNamespace
from unittest.mock import patch


@pytest.mark.asyncio
async def test_execute_stream_endpoint_emits_sse():
    """execute_agent_stream returns text/event-stream and forwards executor
    events as SSE `data:` frames, ending with a done event."""
    from app.routers import agents as ag

    async def fake_stream(self, agent_id, task, user_id, context=None):
        yield {"type": "start", "agent_id": agent_id, "agent_name": "x"}
        yield {"type": "text", "content": "hi"}
        yield {"type": "done", "output": "hi", "execution_time": 0.1, "tool_calls": []}

    with patch("app.services.agent_executor.AgentExecutor.execute_stream", fake_stream):
        resp = await ag.execute_agent_stream(
            agent_id=1,
            body={"task": "hi"},
            current_user=SimpleNamespace(user_id=1),
        )

        assert resp.media_type == "text/event-stream"
        # Drain inside the patch context: body_iterator is a lazy async
        # generator, so the patched execute_stream only runs on iteration.
        chunks = []
        async for c in resp.body_iterator:
            chunks.append(c if isinstance(c, str) else c.decode())
        body = "".join(chunks)
    assert '"type": "start"' in body
    assert '"type": "done"' in body
    assert body.count("data: ") == 3   # one SSE frame per event
