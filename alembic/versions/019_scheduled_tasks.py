"""scheduled_tasks: create table for cron-scheduled jobs

The ScheduledTask model (app/models/schedule.py) was added but no migration ever
created the underlying table, so celery_beat's sync_scheduled_jobs_task failed
on every tick with `relation "scheduled_tasks" does not exist` and retried
forever, spamming the worker log.

This migration creates the table matching the model: id, task_id (UUID,
unique), name, description, cron_expression, task_type, agent_id, task_config
(JSON), is_active, last_run_at, next_run_at, timestamps. Idempotent: skips if
the table already exists.

Revision ID: 019_scheduled_tasks
Revises: 018_audit_logs_columns
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op

revision = "019_scheduled_tasks"
down_revision = "018_audit_logs_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "scheduled_tasks" in inspector.get_table_names():
        return  # already created by a later hand-edit / older script

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cron_expression", sa.String(length=100), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column("task_config", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("scheduled_tasks")
