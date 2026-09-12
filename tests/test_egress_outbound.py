"""Outbound MiniMax/search calls must go through the egress policy."""
import pytest

from app.core.ssrf import SSRFError


@pytest.mark.asyncio
async def test_minimax_embed_blocks_metadata_host():
    from app.services.minimax_embedder import embed_texts
    with pytest.raises((ValueError, SSRFError)):
        await embed_texts(
            ["hello"],
            api_key="k",
            base_url="http://169.254.169.254/",
        )
