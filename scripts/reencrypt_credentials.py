#!/usr/bin/env python3
"""Rewrite pre-AEAD credentials into AES-256-GCM.

Design: docs/superpowers/specs/2026-08-10-server-credential-aead-design.md §6

Deliberately not an alembic migration:
  * it needs ENCRYPTION_KEY, which a deployment pipeline may not have — a
    missing key would turn credential maintenance into a release blocker;
  * a half-finished run inside `alembic upgrade head` is much harder to reason
    about than one inside a script you can simply run again;
  * there is no schema change (all columns are already Text).

Safe to run repeatedly: each value is inspected by format prefix, and anything
already in the new format is skipped. Interrupt it and run it again.

Usage:
    export PYTHONPATH=packages:.
    python scripts/reencrypt_credentials.py --dry-run
    python scripts/reencrypt_credentials.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages"))

from sqlalchemy import text  # noqa: E402

from app.core.security import (  # noqa: E402
    CredentialField,
    DecryptionError,
    decrypt_data,
    encrypt_data,
    is_legacy_ciphertext,
)

# (table, primary key column, ciphertext column, AAD field)
TARGETS = (
    ("providers", "id", "api_key_encrypted", CredentialField.PROVIDER_API_KEY),
    ("mcp_servers", "id", "env_vars_encrypted", CredentialField.MCP_ENV_VARS),
    ("mcp_servers", "id", "auth_token_encrypted", CredentialField.MCP_AUTH_TOKEN),
    ("agent_configs", "id", "env_vars_encrypted", CredentialField.AGENT_ENV_VARS),
    ("env_vars", "id", "value_encrypted", CredentialField.ENV_VAR_VALUE),
    ("n8n_connections", "id", "api_key_encrypted", CredentialField.N8N_API_KEY),
    ("webhooks", "id", "outgoing_secret_encrypted",
     CredentialField.WEBHOOK_OUTGOING_SECRET),
)


class RewriteError(RuntimeError):
    pass


async def rewrite(dry_run: bool) -> int:
    from app.core.database import get_db_context

    converted = skipped = 0

    async with get_db_context() as session:
        for table, pk, column, field in TARGETS:
            try:
                rows = (
                    await session.execute(
                        text(
                            f"SELECT {pk}, {column} FROM {table} "  # noqa: S608
                            f"WHERE {column} IS NOT NULL AND {column} <> ''"
                        )
                    )
                ).all()
            except Exception as exc:  # noqa: BLE001
                print(f"  {table}.{column}: skipped ({type(exc).__name__})")
                continue

            todo = [(rid, val) for rid, val in rows if is_legacy_ciphertext(val)]
            skipped += len(rows) - len(todo)
            if not todo:
                print(f"  {table}.{column}: nothing to do ({len(rows)} already current)")
                continue

            for row_id, value in todo:
                try:
                    plaintext = decrypt_data(value, field)
                except DecryptionError as exc:
                    # Stop rather than skip. Skipping would silently strand a
                    # credential in the old format — and if the key is wrong,
                    # every subsequent row fails the same way and continuing
                    # just produces a longer list of the same problem.
                    raise RewriteError(
                        f"{table}.{column} id={row_id} could not be decrypted. "
                        f"Nothing has been committed. Check ENCRYPTION_KEY."
                    ) from exc

                if not dry_run:
                    await session.execute(
                        text(
                            f"UPDATE {table} SET {column} = :new "  # noqa: S608
                            f"WHERE {pk} = :id"
                        ),
                        {"new": encrypt_data(plaintext, field), "id": row_id},
                    )
                converted += 1

            print(f"  {table}.{column}: {len(todo)} to rewrite")

        if dry_run:
            print("\n[dry-run] rolling back; nothing was written")
            await session.rollback()
        else:
            await session.commit()

    print(f"\nrewritten: {converted}   already current: {skipped}")
    if dry_run and converted:
        print("Re-run without --dry-run to apply.")
    return converted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing",
    )
    args = parser.parse_args()

    print("Rewriting credentials to AES-256-GCM"
          + (" [dry-run]" if args.dry_run else ""))
    try:
        asyncio.run(rewrite(args.dry_run))
    except RewriteError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
