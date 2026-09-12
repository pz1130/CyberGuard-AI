from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import master_config as master_config_router


def _master_config(**overrides):
    values = {
        "id": 1,
        "llm_provider_id": 7,
        "llm_model": "model-a",
        "temperature": 0.7,
        "system_prompt": "system",
        "intent_parser_prompt": "intent",
        "summarizer_prompt": "summary",
        "max_rounds": 10,
        "auto_approve_threshold": 0,
        "branding_logo": None,
        "branding_company_name": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_master_config_response_exposes_provider_id():
    response = master_config_router.MasterConfigResponse.model_validate(_master_config())
    assert response.model_dump()["provider_id"] == 7
    assert response.model == "model-a"


@pytest.mark.asyncio
async def test_master_config_rejects_model_from_another_provider(monkeypatch):
    current = _master_config()
    provider = SimpleNamespace(
        id=8, is_active=True, api_key_encrypted="ciphertext",
        models=[{"name": "model-b"}],
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: provider)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    monkeypatch.setattr(
        master_config_router, "get_master_config", AsyncMock(return_value=current)
    )

    with pytest.raises(HTTPException) as exc:
        await master_config_router.put_config(
            master_config_router.MasterConfigUpdate(provider_id=8, model="model-a"),
            db,
            None,
        )

    assert exc.value.status_code == 400
    assert "does not belong" in exc.value.detail


def test_postgres_checkpoint_dependencies_import():
    import psycopg_pool  # noqa: F401
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: F401
