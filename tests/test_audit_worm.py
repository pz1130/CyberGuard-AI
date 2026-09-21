"""Tests for the audit WORM export service."""
import json
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.services import audit_worm as aw
from app.core.audit import _chain_payload, stamp_chain_hashes
from datetime import datetime

def signed_row(id=5):
    payload = stamp_chain_hashes(_chain_payload(action="x", user_id=1, timestamp=datetime(2026, 9, 18)), "0" * 64)
    payload["timestamp"] = datetime(2026, 9, 18)
    return SimpleNamespace(id=id, **payload)


def test_serialize_jsonl_includes_chain_fields():
    rows = [SimpleNamespace(id=1, action="gatekeeper:allow", entry_hash="e1", prev_hash="0"*64,
                            input_hash="i1", output_hash="o1", timestamp=None, agent_name="a",
                            action_category="observe", confidence=None, human_reviewer=None,
                            rollback_possible=None, risk_tier="low", request_id="r1", user_id=1,
                            agent_id=None)]
    text = aw._serialize_jsonl(rows)
    line = json.loads(text.strip())
    assert line["entry_hash"] == "e1" and line["prev_hash"] == "0"*64
    assert line["id"] == 1 and line["action"] == "gatekeeper:allow"


@pytest.mark.asyncio
async def test_export_advances_marker_and_uploads():
    rows = [signed_row()]
    with patch("app.services.audit_integrity.inspect_chain", AsyncMock(return_value={"fully_verified": True, "status": "verified"})), \
         patch.object(aw, "verify_external_evidence", AsyncMock(return_value={"status": "no_archives"})), \
         patch.object(aw, "_fetch_rows_after", AsyncMock(return_value=rows)), \
         patch.object(aw, "_put_worm_object", AsyncMock(return_value="audit/worm/1-5.jsonl")), \
         patch.object(aw, "_record_marker", AsyncMock()) as marker:
        summary = await aw.export_new(retain_days=365)
    assert summary["rows"] == 1 and summary["last_audit_id"] == 5
    marker.assert_awaited()


@pytest.mark.asyncio
async def test_export_noop_when_nothing_new():
    with patch("app.services.audit_integrity.inspect_chain", AsyncMock(return_value={"fully_verified": True, "status": "verified"})), \
         patch.object(aw, "verify_external_evidence", AsyncMock(return_value={"status": "verified", "last_archived_row_id": 10})), \
         patch.object(aw, "_fetch_rows_after", AsyncMock(return_value=[])):
        summary = await aw.export_new()
    assert summary["rows"] == 0 and summary.get("object_key") is None
