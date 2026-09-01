"""Create Scout Runs, Agent Tasks, usage events, and leased jobs.

Revision ID: 0003_runs_jobs
Revises: 0002_competitors
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_runs_jobs"
down_revision: str | Sequence[str] | None = "0002_competitors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    run_type = postgresql.ENUM(
        "source_discovery",
        "daily_scout",
        "manual_scout",
        "weekly_brief",
        name="run_type",
    )
    scout_run_status = postgresql.ENUM(
        "queued",
        "planning",
        "gathering",
        "synthesizing",
        "completed",
        "partial",
        "failed",
        name="scout_run_status",
    )
    agent_task_role = postgresql.ENUM(
        "main_planner",
        "child_researcher",
        "main_synthesizer",
        name="agent_task_role",
    )
    agent_task_status = postgresql.ENUM(
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
        name="agent_task_status",
    )
    job_status = postgresql.ENUM(
        "queued",
        "leased",
        "completed",
        "failed",
        name="job_status",
    )

    op.create_table(
        "scout_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_type", run_type, nullable=False),
        sa.Column("status", scout_run_status, server_default="queued", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column(
            "partial_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=True),
        sa.Column(
            "settled_cost_usd",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "(run_type = 'weekly_brief' AND competitor_id IS NULL) "
            "OR (run_type <> 'weekly_brief' AND competitor_id IS NOT NULL)",
            name="ck_scout_runs_competitor_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scout_runs_user_id", "scout_runs", ["user_id"])
    op.create_index("ix_scout_runs_competitor_id", "scout_runs", ["competitor_id"])
    op.create_index(
        "ix_scout_runs_user_created",
        "scout_runs",
        ["user_id", "created_at", "id"],
    )
    op.create_index(
        "uq_scout_runs_active_competitor_scout",
        "scout_runs",
        ["competitor_id"],
        unique=True,
        postgresql_where=sa.text(
            "competitor_id IS NOT NULL "
            "AND run_type IN ('daily_scout', 'manual_scout') "
            "AND status IN ('queued', 'planning', 'gathering', 'synthesizing')"
        ),
    )
    op.create_index(
        "uq_scout_runs_competitor_schedule",
        "scout_runs",
        ["run_type", "competitor_id", "scheduled_for"],
        unique=True,
        postgresql_where=sa.text("competitor_id IS NOT NULL"),
    )
    op.create_index(
        "uq_scout_runs_weekly_schedule",
        "scout_runs",
        ["run_type", "user_id", "scheduled_for"],
        unique=True,
        postgresql_where=sa.text("competitor_id IS NULL AND run_type = 'weekly_brief'"),
    )

    op.create_table(
        "agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("role", agent_task_role, nullable=False),
        sa.Column("task_kind", sa.String(length=100), nullable=False),
        sa.Column("status", agent_task_status, server_default="queued", nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column(
            "source_scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("otari_request_id", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=True),
        sa.Column(
            "settled_cost_usd",
            sa.Numeric(precision=18, scale=6),
            nullable=True,
        ),
        sa.Column("pricing_source", sa.String(length=100), nullable=True),
        sa.Column(
            "validated_output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["parent_task_id"],
            ["agent_tasks.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["scout_run_id"], ["scout_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_tasks_scout_run_id", "agent_tasks", ["scout_run_id"])
    op.create_index("ix_agent_tasks_parent_task_id", "agent_tasks", ["parent_task_id"])
    op.create_index("ix_agent_tasks_otari_request_id", "agent_tasks", ["otari_request_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_request_id", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=True),
        sa.Column("settled_cost_usd", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("pricing_source", sa.String(length=100), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scout_run_id"], ["scout_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
    op.create_index("ix_usage_events_scout_run_id", "usage_events", ["scout_run_id"])
    op.create_index("ix_usage_events_agent_task_id", "usage_events", ["agent_task_id"])
    op.create_index(
        "ix_usage_events_provider_request_id",
        "usage_events",
        ["provider_request_id"],
    )
    op.create_index("ix_usage_events_occurred_at", "usage_events", ["occurred_at"])
    op.create_index(
        "ix_usage_events_user_occurred",
        "usage_events",
        ["user_id", "occurred_at", "id"],
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("deduplication_key", sa.String(length=500), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", job_status, server_default="queued", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_deduplication_key", "jobs", ["deduplication_key"], unique=True)
    op.create_index(
        "ix_jobs_claimable",
        "jobs",
        ["status", "available_at", "created_at", "id"],
    )
    op.create_index("ix_jobs_lease_expiry", "jobs", ["status", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_lease_expiry", table_name="jobs")
    op.drop_index("ix_jobs_claimable", table_name="jobs")
    op.drop_index("ix_jobs_deduplication_key", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_usage_events_user_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_occurred_at", table_name="usage_events")
    op.drop_index("ix_usage_events_provider_request_id", table_name="usage_events")
    op.drop_index("ix_usage_events_agent_task_id", table_name="usage_events")
    op.drop_index("ix_usage_events_scout_run_id", table_name="usage_events")
    op.drop_index("ix_usage_events_user_id", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_agent_tasks_otari_request_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_parent_task_id", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_scout_run_id", table_name="agent_tasks")
    op.drop_table("agent_tasks")

    op.drop_index("uq_scout_runs_weekly_schedule", table_name="scout_runs")
    op.drop_index("uq_scout_runs_competitor_schedule", table_name="scout_runs")
    op.drop_index("uq_scout_runs_active_competitor_scout", table_name="scout_runs")
    op.drop_index("ix_scout_runs_user_created", table_name="scout_runs")
    op.drop_index("ix_scout_runs_competitor_id", table_name="scout_runs")
    op.drop_index("ix_scout_runs_user_id", table_name="scout_runs")
    op.drop_table("scout_runs")

    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS agent_task_status")
    op.execute("DROP TYPE IF EXISTS agent_task_role")
    op.execute("DROP TYPE IF EXISTS scout_run_status")
    op.execute("DROP TYPE IF EXISTS run_type")
