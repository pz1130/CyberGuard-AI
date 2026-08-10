"""Count credentials still stored in the pre-AEAD (unauthenticated) format.

Design: docs/superpowers/specs/2026-08-10-server-credential-aead-design.md §10.3

The migration is lazy — `decrypt_data` reads both formats forever, so nothing
breaks if the rewrite script is never run. That convenience is exactly the risk:
without something that keeps saying so, existing ciphertext stays malleable
indefinitely and nobody notices. This scan runs at startup, logs at a level
matched to what it finds, and is exposed so the WebUI can show it.

It only inspects the format prefix. It never decrypts, so it needs no key and
cannot fail in a way that reveals anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text

from app.core.security import is_legacy_ciphertext

logger = logging.getLogger(__name__)


# (table, column) — the set the rewrite script also walks. Keep in step.
SCANNED_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("providers", "api_key_encrypted"),
    ("mcp_servers", "env_vars_encrypted"),
    ("mcp_servers", "auth_token_encrypted"),
    ("agent_configs", "env_vars_encrypted"),
    ("env_vars", "value_encrypted"),
    ("n8n_connections", "api_key_encrypted"),
    ("webhooks", "outgoing_secret_encrypted"),
)


@dataclass
class EncryptionStatus:
    """Result of the most recent scan. All-zero means fully migrated."""

    legacy_total: int = 0
    by_column: Dict[str, int] = field(default_factory=dict)
    scanned: bool = False
    error: Optional[str] = None

    @property
    def fully_migrated(self) -> bool:
        return self.scanned and self.error is None and self.legacy_total == 0

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "fully_migrated": self.fully_migrated,
            "legacy_total": self.legacy_total,
            "by_column": dict(self.by_column),
            "error": self.error,
            "detail": (
                "All stored credentials use authenticated encryption (AES-256-GCM)."
                if self.fully_migrated
                else
                "Some credentials are still stored with unauthenticated AES-CBC. "
                "They can be read normally, but a database write can alter them "
                "undetected. Run scripts/reencrypt_credentials.py."
            ),
        }


_status = EncryptionStatus()


def get_encryption_status() -> EncryptionStatus:
    return _status


async def scan_legacy_credentials() -> EncryptionStatus:
    """Count legacy-format values across the credential columns."""
    from app.core.database import get_db_context

    status = EncryptionStatus()
    try:
        async with get_db_context() as session:
            for table, column in SCANNED_COLUMNS:
                try:
                    result = await session.execute(
                        text(
                            f"SELECT {column} FROM {table} "  # noqa: S608 - fixed identifiers
                            f"WHERE {column} IS NOT NULL AND {column} <> ''"
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    # A table this deployment has not migrated to yet is not a
                    # reason to fail the whole scan.
                    logger.debug("encryption scan skipped %s.%s: %s", table, column, exc)
                    continue

                legacy = sum(1 for (value,) in result if is_legacy_ciphertext(value))
                if legacy:
                    status.by_column[f"{table}.{column}"] = legacy
                    status.legacy_total += legacy
        status.scanned = True
    except Exception as exc:  # noqa: BLE001
        # Report the failure rather than silently claiming a clean bill of
        # health — "0 legacy" and "could not check" must not look the same.
        status.error = f"{type(exc).__name__}: {exc}"
        logger.warning("credential encryption scan failed: %s", status.error)

    _apply(status)
    return status


def _apply(status: EncryptionStatus) -> None:
    global _status
    _status = status

    if status.error:
        return
    if status.legacy_total == 0:
        logger.info("credential encryption: all values use AES-256-GCM")
        return

    breakdown: List[str] = [f"{k}={v}" for k, v in sorted(status.by_column.items())]
    logger.warning(
        "credential encryption: %d value(s) still use unauthenticated AES-CBC "
        "and can be modified undetectably by anyone with database write access "
        "(%s). Run scripts/reencrypt_credentials.py to rewrite them.",
        status.legacy_total,
        ", ".join(breakdown),
    )
