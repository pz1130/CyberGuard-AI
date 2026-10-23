"""Prevent user cleanup from rewriting signed audit payloads."""
from alembic import op
import sqlalchemy as sa

revision = "047_preserve_audit_actors"
down_revision = "046_email_config"
branch_labels = None
depends_on = None


def _replace_actor_foreign_key(ondelete):
    for fk in sa.inspect(op.get_bind()).get_foreign_keys("audit_logs"):
        if fk["constrained_columns"] == ["user_id"]:
            op.drop_constraint(fk["name"], "audit_logs", type_="foreignkey")
    op.create_foreign_key(
        "audit_logs_user_id_fkey", "audit_logs", "users",
        ["user_id"], ["id"], ondelete=ondelete,
    )


def upgrade():
    # No historical payloads or signatures are rewritten.
    _replace_actor_foreign_key("RESTRICT")


def downgrade():
    _replace_actor_foreign_key("SET NULL")
