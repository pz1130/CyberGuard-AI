"""Clear conversation titles that are a frozen UI placeholder.

Until 077f3c3 the chat client sent its own translated "New Chat" as the title
of a new conversation, freezing whichever language was active into the row.
040 stopped the database supplying `'新对话'` as a column default, but neither
change touched existing rows — so an English UI still showed `新建对话` in the
sidebar, because the title was not empty and the client's localised fallback
never ran.

A NULL title renders the reader's own translation and stays eligible for
auto-titling, which keys off absence.

Revision ID: 042_clear_placeholder_titles  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 041_conversation_messages
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "042_clear_placeholder_titles"
down_revision: Union[str, None] = "041_conversation_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Kept literal rather than imported: a migration must keep meaning the same
# thing even if the application's list is edited later.
_PLACEHOLDERS = ("新对话", "新建对话", "New Chat", "New Conversation")


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE conversations SET title = NULL "
            "WHERE title IS NOT NULL AND btrim(title) = ANY(:placeholders)"
        ),
        {"placeholders": list(_PLACEHOLDERS)},
    )


def downgrade() -> None:
    # Not reversible: which placeholder each row held, and in which language,
    # is exactly the information this migration exists to discard. Restoring a
    # guess would re-create the bug in a new language.
    pass
