import io
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from app.services import audit_worm as aw
from app.routers.providers import _minimax_preset_region
from tests.test_audit_integrity import chain, current


def test_archive_verification_reads_second_page_and_detects_mismatch():
    rows = chain(2)
    client = MagicMock()
    client.list_object_versions.side_effect = [
        {'Versions': [{'Key': 'a', 'VersionId': 'v1'}], 'IsTruncated': True,
         'NextKeyMarker': 'a', 'NextVersionIdMarker': 'v1'},
        {'Versions': [{'Key': 'b', 'VersionId': 'v2'}]}]
    client.get_object_retention.return_value = {'Retention': {
        'Mode': 'COMPLIANCE', 'RetainUntilDate': datetime.now(timezone.utc) + timedelta(days=1)}}
    client.get_object.side_effect = [
        {'Body': io.BytesIO(aw._serialize_jsonl(rows[:1]).encode())},
        {'Body': io.BytesIO(aw._serialize_jsonl(rows[1:]).encode())}]
    local = current(rows)
    local[2]['action'] = 'changed'
    with patch.object(aw, '_s3_client', return_value=(client, 'bucket')):
        report = aw.compare_archives(aw._iter_external_archives(), local)
    assert report['mismatch_row_ids'] == [2]
    assert report['objects_checked'] == 2
    assert client.list_object_versions.call_args.kwargs['VersionIdMarker'] == 'v1'


@pytest.mark.parametrize('url', [
    'https://gateway.example/v1', 'https://api.minimax.io.attacker.test/v1',
    'https://api.minimax.io/custom', 'https://gateway.example/api.minimax.cn/v1',
])
def test_custom_minimax_endpoints_are_not_migration_targets(url):
    assert _minimax_preset_region(url) is None


@pytest.mark.parametrize('url,region', [
    ('https://api.minimaxi.com/v1', '国内版'),
    ('https://api.minimax.cn/v1/', '国内版'),
    ('https://api.minimax.io/anthropic', '海外版'),
])
def test_known_minimax_presets_are_migrated(url, region):
    assert _minimax_preset_region(url) == region


@pytest.mark.asyncio
@pytest.mark.parametrize('environment,opt_in', [
    ('production', 'true'), ('development', 'true'), ('testing', None),
])
async def test_smoke_setup_rejects_unsafe_environment_before_database(monkeypatch, environment, opt_in):
    from app.config import settings
    from tests import test_smoke_api as smoke
    monkeypatch.setattr(settings, 'ENVIRONMENT', environment)
    if opt_in:
        monkeypatch.setenv('ALLOW_SMOKE_MUTATIONS', opt_in)
    else:
        monkeypatch.delenv('ALLOW_SMOKE_MUTATIONS', raising=False)
    with patch.object(smoke, 'get_db_context') as db:
        with pytest.raises(RuntimeError, match='disposable'):
            await smoke._ensure_smoke_fixtures()
        db.assert_not_called()


def test_smoke_setup_allows_explicit_testing_environment(monkeypatch):
    from app.config import settings
    from tests.test_smoke_api import _require_disposable_smoke_environment
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'testing')
    monkeypatch.setenv('ALLOW_SMOKE_MUTATIONS', 'true')
    _require_disposable_smoke_environment()
