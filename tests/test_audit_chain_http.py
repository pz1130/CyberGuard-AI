"""HTTP audit rows must join the tamper-evident hash chain."""
from app.core.audit import _canonical, _hash_data, stamp_chain_hashes


def test_stamp_chain_hashes_links_to_previous():
    genesis = "0" * 64
    payload = {
        "user_id": 1,
        "agent_id": None,
        "action": "GET /api/v1/health",
        "input_hash": _hash_data({"path": "/x"}),
        "output_hash": _hash_data({"status_code": 200}),
        "request_id": "abc",
        "timestamp": "2026-09-12T10:00:00",
    }
    first = stamp_chain_hashes(payload, genesis)
    assert first["prev_hash"] == genesis
    assert len(first["entry_hash"]) == 64
    second = stamp_chain_hashes({**payload, "request_id": "def"}, first["entry_hash"])
    assert second["prev_hash"] == first["entry_hash"]
    assert second["entry_hash"] != first["entry_hash"]
    assert _canonical({"a": 1}) == '{"a": 1}'
