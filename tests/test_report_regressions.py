"""Regression checks for the September UI test report."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql


@pytest.mark.asyncio
async def test_audit_search_filters_before_pagination_and_counts_same_matches():
    from app.routers.audit import list_audit_logs

    count = MagicMock()
    count.scalar.return_value = 21
    rows = MagicMock()
    rows.scalars.return_value.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[count, rows])
    result = await list_audit_logs(
        skip=0, limit=50, q='login%', user_id=None, agent_id=None,
        action=None, db=db, _=None,
    )
    assert result.total == 21
    for call in db.execute.call_args_list:
        compiled = call.args[0].compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert 'WHERE' in sql
        assert 'ESCAPE' in sql
        assert 'login/%' in compiled.params.values()
    sql = str(db.execute.call_args_list[1].args[0])
    assert sql.index('WHERE') < sql.index('LIMIT')


@pytest.mark.asyncio
@pytest.mark.parametrize('bound,ready', [(False, False), (True, True)])
async def test_chat_readiness_reports_binding_without_prompts(monkeypatch, bound, ready):
    from types import SimpleNamespace
    from app.routers.chat import chat_readiness
    from app.services import master_config

    monkeypatch.setattr(master_config, 'get_master_config', AsyncMock(return_value=SimpleNamespace(
        llm_provider_id=1 if bound else None,
        llm_model='model' if bound else None,
        system_prompt='private',
    )))
    assert await chat_readiness(db=MagicMock(), _=None) == {'master_ready': ready}
