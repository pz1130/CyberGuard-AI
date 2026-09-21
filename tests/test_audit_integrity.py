"""Distinguish payload damage, chain damage, coverage and external evidence."""
import io
import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.audit import _chain_payload, stamp_chain_hashes
from app.services.audit_integrity import inspect_rows
from app.services import audit_worm as aw


def chain(count=2):
    rows = []
    prev = '0' * 64
    for i in range(1, count + 1):
        timestamp = datetime(2026, 9, 18, 10, 0, i)
        payload = stamp_chain_hashes(_chain_payload(user_id=17, action='test', timestamp=timestamp,
            ip_address='127.0.0.1', metadata_json={'status': 200}), prev)
        prev = payload['entry_hash']
        payload['timestamp'] = timestamp
        rows.append(SimpleNamespace(id=i, **payload))
    return rows


def archive(rows, locked=True):
    return {'key': 'audit/worm/test.jsonl', 'version_id': 'v1', 'locked': locked,
            'sha256': 'test', 'records': [json.loads(line) for line in aw._serialize_jsonl(rows).splitlines()]}


def current(rows):
    return {r.id: json.loads(aw._serialize_jsonl([r])) for r in rows}


def test_actor_damage_is_not_a_link_mismatch():
    rows = chain()
    rows[0].user_id = None
    report = inspect_rows(rows)
    assert report['payload_mismatches'] == 1
    assert report['link_mismatches'] == 0
    assert report['first_broken_row_id'] == 1
    assert report['issues'][0]['reasons'] == ['payload_mismatch']
    assert report['status'] == 'broken'


def test_links_are_checked_and_issue_list_is_bounded_without_losing_counts():
    rows = chain(3)
    for row in rows:
        row.prev_hash = 'bad'
    report = inspect_rows(rows, limit=1)
    assert report['affected_rows'] == 3
    assert report['link_mismatches'] == 3
    assert len(report['issues']) == 1
    assert report['issues_truncated']


@pytest.mark.parametrize('version', [None, 1, 99])
def test_old_or_unknown_versions_do_not_claim_full_verification(version):
    rows = chain(1)
    rows[0].chain_version = version
    report = inspect_rows(rows)
    assert report['status'] == 'partial'
    assert not report['fully_verified']


def test_empty_and_unsigned_data_do_not_pass():
    assert inspect_rows([])['status'] == 'empty'
    rows = chain(1)
    rows[0].entry_hash = None
    assert inspect_rows(rows)['unsigned_rows'] == 1
    assert not inspect_rows(rows)['fully_verified']


def test_external_serialization_covers_all_signed_fields_and_revalidates():
    rows = chain()
    records = archive(rows)['records']
    rebuilt = [SimpleNamespace(**record) for record in records]
    assert inspect_rows(rebuilt)['fully_verified']
    assert 'metadata_json' in records[0] and 'chain_version' in records[0]


def test_external_evidence_detects_locally_rehashed_history_and_tail_deletion():
    rows = chain()
    saved = archive(rows)
    rows[0].action = 'rewritten'
    prev = '0' * 64
    from app.core.audit import _row_chain_payload
    for row in rows:
        signed = stamp_chain_hashes(_row_chain_payload(row), prev)
        row.prev_hash = prev
        row.entry_hash = signed['entry_hash']
        prev = row.entry_hash
    assert inspect_rows(rows)['fully_verified']
    report = aw.compare_archives([saved], current(rows))
    assert report['status'] == 'mismatch' and report['mismatch_count'] == 2
    original = chain()
    report = aw.compare_archives([archive(original)], current(original[:1]))
    assert report['mismatch_row_ids'] == [2]


def test_external_status_requires_locks_complete_fields_and_complete_inventory():
    rows = chain()
    assert aw.compare_archives([archive(rows)], current(rows))['verified']
    assert not aw.compare_archives([archive(rows, locked=False)], current(rows))['verified']
    assert not aw.compare_archives([archive(rows)], current(rows), partial=True)['verified']
    saved = archive(rows)
    del saved['records'][0]['metadata_json']
    assert aw.compare_archives([saved], current(rows))['status'] == 'partial'
    # A later archive cannot hide a missing earlier archive.
    assert aw.compare_archives([archive(rows[1:])], current(rows))['status'] == 'partial'


@pytest.mark.asyncio
async def test_damaged_data_is_not_uploaded_as_verified_evidence():
    with patch('app.services.audit_integrity.inspect_chain', AsyncMock(return_value={
        'fully_verified': False, 'status': 'broken'})), patch.object(aw, '_put_worm_object', AsyncMock()) as upload:
        with pytest.raises(aw.AuditExportBlocked):
            await aw.export_new()
        upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_readback_checks_exact_object_version_and_retention():
    body = b'archive'
    client = MagicMock()
    client.put_object.return_value = {'VersionId': 'v1'}
    client.get_object_retention.side_effect = lambda **kw: {'Retention': {
        'Mode': 'COMPLIANCE', 'RetainUntilDate': client.put_object.call_args.kwargs['ObjectLockRetainUntilDate']}}
    client.get_object.return_value = {'Body': io.BytesIO(body)}
    with patch.object(aw, '_s3_client', return_value=(client, 'bucket')):
        assert await aw._put_worm_object('key', body, datetime.now(timezone.utc) + timedelta(days=365)) == 'key'
    assert client.get_object.call_args.kwargs['VersionId'] == 'v1'
    assert client.put_object.call_args.kwargs['ObjectLockRetainUntilDate'].microsecond == 0
    client.get_object.return_value = {'Body': io.BytesIO(b'changed')}
    with patch.object(aw, '_s3_client', return_value=(client, 'bucket')):
        with pytest.raises(RuntimeError, match='differs'):
            await aw._put_worm_object('key', body, datetime.now(timezone.utc) + timedelta(days=365))


def test_retention_rejects_governance_or_expired_locks():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert not aw._retention_valid({'Mode': 'GOVERNANCE', 'RetainUntilDate': future})
    assert not aw._retention_valid({'Mode': 'COMPLIANCE', 'RetainUntilDate': future - timedelta(days=2)})


def test_remote_version_inventory_keeps_overwritten_original_visible():
    rows = chain(1)
    original = aw._serialize_jsonl(rows).encode()
    client = MagicMock()
    client.list_object_versions.return_value = {'Versions': [
        {'Key': 'audit/worm/x', 'VersionId': 'original', 'Size': len(original)},
        {'Key': 'audit/worm/x', 'VersionId': 'replacement', 'Size': len(original)}]}
    client.get_object_retention.return_value = {'Retention': {
        'Mode': 'COMPLIANCE', 'RetainUntilDate': datetime.now(timezone.utc) + timedelta(days=1)}}
    client.get_object.side_effect = lambda **kw: {'Body': io.BytesIO(original)}
    with patch.object(aw, '_s3_client', return_value=(client, 'bucket')):
        archives, partial = aw._read_external_archives()
    assert not partial
    assert {a['version_id'] for a in archives} == {'original', 'replacement'}
    assert {c.kwargs['VersionId'] for c in client.get_object.call_args_list} == {'original', 'replacement'}


@pytest.mark.asyncio
async def test_compatibility_verifier_does_not_accept_partial_coverage():
    from app.core.audit import verify_chain
    with patch('app.services.audit_integrity.inspect_chain', AsyncMock(return_value={
        'fully_verified': False, 'first_broken_row_id': None})):
        assert await verify_chain() == (False, None)


def test_periodic_archival_is_opt_in(monkeypatch):
    from app.workers.tasks import archive_audit_evidence_task
    monkeypatch.delenv('AUDIT_WORM_AUTO_EXPORT', raising=False)
    assert archive_audit_evidence_task.run() == {'status': 'disabled'}
