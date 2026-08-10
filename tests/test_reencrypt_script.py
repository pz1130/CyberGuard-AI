"""The rewrite script must be idempotent, dry-runnable, and abort cleanly.

Exercised against a throwaway table rather than the real credential tables, so
the suite never rewrites anyone's actual secrets.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.security import (
    AESCipher,
    CredentialField,
    encrypt_data,
    is_legacy_ciphertext,
)
from app.config import settings

REPO = Path(__file__).resolve().parent.parent
TABLE = "test_reencrypt_fixture"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "reencrypt_credentials", REPO / "scripts" / "reencrypt_credentials.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def fixture_table():
    """A table shaped like a credential table, seeded with legacy ciphertext."""
    from app.core.database import get_db_context

    legacy = AESCipher(settings.ENCRYPTION_KEY).encrypt
    async with get_db_context() as session:
        await session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await session.execute(
            text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, secret TEXT)")
        )
        for value in ("alpha-secret", "beta-secret"):
            await session.execute(
                text(f"INSERT INTO {TABLE} (secret) VALUES (:v)"),
                {"v": legacy(value)},
            )
        # one row already migrated — the script must leave it alone
        await session.execute(
            text(f"INSERT INTO {TABLE} (secret) VALUES (:v)"),
            {"v": encrypt_data("gamma-secret", CredentialField.ENV_VAR_VALUE)},
        )
        await session.commit()

    yield TABLE

    async with get_db_context() as session:
        await session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await session.commit()


async def _secrets():
    from app.core.database import get_db_context

    async with get_db_context() as session:
        rows = (await session.execute(text(f"SELECT secret FROM {TABLE} ORDER BY id"))).all()
    return [r[0] for r in rows]


@pytest.mark.asyncio
async def test_dry_run_reports_without_writing(fixture_table, monkeypatch):
    script = _load_script()
    monkeypatch.setattr(
        script, "TARGETS", ((TABLE, "id", "secret", CredentialField.ENV_VAR_VALUE),)
    )

    before = await _secrets()
    converted = await script.rewrite(dry_run=True)

    assert converted == 2  # the two legacy rows, not the migrated one
    assert await _secrets() == before, "dry-run must not write"


@pytest.mark.asyncio
async def test_rewrite_converts_legacy_and_is_idempotent(fixture_table, monkeypatch):
    script = _load_script()
    monkeypatch.setattr(
        script, "TARGETS", ((TABLE, "id", "secret", CredentialField.ENV_VAR_VALUE),)
    )

    assert await script.rewrite(dry_run=False) == 2
    after = await _secrets()
    assert not any(is_legacy_ciphertext(v) for v in after)

    # running again finds nothing left to do
    assert await script.rewrite(dry_run=False) == 0
    assert await _secrets() == after, "a second run must not churn ciphertext"


@pytest.mark.asyncio
async def test_rewritten_values_still_decrypt_to_the_same_plaintext(
    fixture_table, monkeypatch
):
    """The whole point: re-encryption must be lossless."""
    from app.core.security import decrypt_data

    script = _load_script()
    monkeypatch.setattr(
        script, "TARGETS", ((TABLE, "id", "secret", CredentialField.ENV_VAR_VALUE),)
    )
    await script.rewrite(dry_run=False)

    plaintexts = [
        decrypt_data(v, CredentialField.ENV_VAR_VALUE) for v in await _secrets()
    ]
    assert plaintexts == ["alpha-secret", "beta-secret", "gamma-secret"]


@pytest.mark.asyncio
async def test_an_undecryptable_row_aborts_without_committing(
    fixture_table, monkeypatch
):
    """Skipping would silently strand a credential in the old format."""
    from app.core.database import get_db_context

    async with get_db_context() as session:
        await session.execute(
            text(f"INSERT INTO {TABLE} (secret) VALUES (:v)"),
            {"v": "bm90LWEtdmFsaWQtY2lwaGVydGV4dA=="},  # legacy-shaped garbage
        )
        await session.commit()

    script = _load_script()
    monkeypatch.setattr(
        script, "TARGETS", ((TABLE, "id", "secret", CredentialField.ENV_VAR_VALUE),)
    )

    before = await _secrets()
    with pytest.raises(script.RewriteError) as ei:
        await script.rewrite(dry_run=False)

    assert "ENCRYPTION_KEY" in str(ei.value)
    assert await _secrets() == before, "a failed run must commit nothing"
