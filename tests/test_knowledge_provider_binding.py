from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.knowledge import _validate_embedding_selection


class _DB:
    def __init__(self, provider):
        self.provider = provider

    async def get(self, _model, provider_id):
        return self.provider if self.provider and self.provider.id == provider_id else None


@pytest.mark.asyncio
async def test_embedding_selection_requires_configured_key():
    provider = SimpleNamespace(
        id=7, is_active=True, api_key_encrypted=None,
        models=[{"name": "embed-a", "model_type": "embedding"}],
    )
    with pytest.raises(HTTPException, match="configured API key"):
        await _validate_embedding_selection(_DB(provider), 7, "embed-a")


@pytest.mark.asyncio
async def test_embedding_selection_rejects_model_from_other_provider():
    provider = SimpleNamespace(
        id=7, is_active=True, api_key_encrypted="ciphertext",
        models=[{"name": "embed-a", "model_type": "embedding"}],
    )
    with pytest.raises(HTTPException, match="does not belong"):
        await _validate_embedding_selection(_DB(provider), 7, "embed-b")


@pytest.mark.asyncio
async def test_embedding_selection_accepts_exact_provider_model_pair():
    provider = SimpleNamespace(
        id=7, is_active=True, api_key_encrypted="ciphertext",
        models=[{"name": "embed-a", "model_type": "embedding"}],
    )
    assert await _validate_embedding_selection(_DB(provider), 7, "embed-a") is provider
