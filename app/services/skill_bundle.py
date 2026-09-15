"""Skill bundle digest and loading.

The digest is what makes approval bind to specific code: a Tool promoted from
a bundle stores the digest of that bundle, so a later re-import with different
script contents cannot reuse the old approval.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any, List, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def file_bytes(row: Any) -> bytes:
    """Content of a SkillFile row, whichever column it landed in."""
    if row.content_text is not None:
        return row.content_text.encode("utf-8")
    return row.content_blob or b""


def bundle_digest(files: Sequence[Tuple[str, bytes]]) -> str:
    """sha256 over the whole bundle, sorted by path.

    Each path and each body is length-prefixed so that moving the boundary
    between them cannot produce the same digest for a different bundle.
    """
    h = hashlib.sha256()
    for path, content in sorted(files, key=lambda f: f[0]):
        raw_path = path.encode("utf-8")
        h.update(struct.pack(">I", len(raw_path)))
        h.update(raw_path)
        h.update(struct.pack(">Q", len(content)))
        h.update(content)
    return h.hexdigest()


async def load_bundle(db: AsyncSession, skill_id: int) -> List[Tuple[str, bytes]]:
    """Every bundled file of a skill as (path, bytes), sorted by path."""
    from app.models.skill import SkillFile

    rows = (
        await db.execute(
            select(SkillFile).where(SkillFile.skill_id == skill_id).order_by(SkillFile.path)
        )
    ).scalars().all()
    return [(r.path, file_bytes(r)) for r in rows]


async def bundle_digest_for_skill(db: AsyncSession, skill_id: int) -> str:
    return bundle_digest(await load_bundle(db, skill_id))
