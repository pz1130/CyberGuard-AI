"""Drop security settings that nothing ever read.

Five of the six columns on this table were inert. Three were booleans whose
only possible meaning was "turn a security control off" — store credentials in
plaintext, skip permission checks, stop writing the audit trail. A security
product should not offer those actions, so they are invariants rather than
configuration, and the fix is to remove the switches, not to wire them up.

`api_key_rotation_days` named a feature that was never built.

`max_login_attempts` was the one dead setting worth keeping: it names a real
control, and it is now enforced by app/core/login_guard.py.
`session_timeout_minutes` was wired up in f9824c0.

Revision ID: 043_drop_dead_security_toggles  (<=32 chars: alembic_version.version_num is varchar(32))
Revises: 042_clear_placeholder_titles
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "043_drop_dead_security_toggles"
down_revision: Union[str, None] = "042_clear_placeholder_titles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in ("encryption_enabled", "rbac_enabled", "audit_logging",
                   "api_key_rotation_days"):
        op.drop_column("security_settings", column)


def downgrade() -> None:
    # Restored with the values they always held, since nothing ever read them
    # to be anything else.
    op.add_column("security_settings", sa.Column(
        "encryption_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("security_settings", sa.Column(
        "rbac_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("security_settings", sa.Column(
        "audit_logging", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("security_settings", sa.Column(
        "api_key_rotation_days", sa.Integer(), nullable=False, server_default="90"))
