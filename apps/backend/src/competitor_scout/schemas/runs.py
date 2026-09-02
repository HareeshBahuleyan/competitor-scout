from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from competitor_scout.models.intelligence import (
    AgentTaskRole,
    AgentTaskStatus,
    RunType,
    ScoutRunStatus,
)

_ALLOWED_TRANSITIONS = {
    ScoutRunStatus.QUEUED: {
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.PLANNING: {
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.GATHERING: {
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.SYNTHESIZING: {
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
}

_DAILY_TRANSITIONS = {
    ScoutRunStatus.QUEUED: {
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.PLANNING: {
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.GATHERING: {
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.SYNTHESIZING: {
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
}

_SOURCE_DISCOVERY_TRANSITIONS = {
    ScoutRunStatus.QUEUED: {
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.PLANNING: {
        ScoutRunStatus.GATHERING,
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.GATHERING: {
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
}

_WEEKLY_TRANSITIONS = {
    ScoutRunStatus.QUEUED: {
        ScoutRunStatus.PLANNING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.PLANNING: {
        ScoutRunStatus.SYNTHESIZING,
        ScoutRunStatus.FAILED,
    },
    ScoutRunStatus.SYNTHESIZING: {
        ScoutRunStatus.COMPLETED,
        ScoutRunStatus.PARTIAL,
        ScoutRunStatus.FAILED,
    },
}

_TRANSITIONS_BY_RUN_TYPE = {
    RunType.DAILY_SCOUT: _DAILY_TRANSITIONS,
    RunType.MANUAL_SCOUT: _DAILY_TRANSITIONS,
    RunType.SOURCE_DISCOVERY: _SOURCE_DISCOVERY_TRANSITIONS,
    RunType.WEEKLY_BRIEF: _WEEKLY_TRANSITIONS,
}


def transition_allowed(
    current: ScoutRunStatus,
    target: ScoutRunStatus,
    *,
    run_type: RunType | None = None,
) -> bool:
    transitions = _ALLOWED_TRANSITIONS if run_type is None else _TRANSITIONS_BY_RUN_TYPE[run_type]
    if target not in transitions.get(current, set()):
        raise ValueError(f"invalid Scout Run transition: {current} -> {target}")
    return True


class RunRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    competitor_id: UUID | None
    run_type: RunType
    status: ScoutRunStatus
    scheduled_for: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_code: str | None
    failure_summary: str | None
    partial_reasons: list[str]
    partial_summaries: list[str]
    input_tokens: int
    output_tokens: int
    tool_calls: int | None
    settled_cost_usd: Decimal | None
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    scout_run_id: UUID
    parent_task_id: UUID | None
    role: AgentTaskRole
    task_kind: str
    status: AgentTaskStatus
    model: str
    objective: str
    source_scope: list[str]
    attempt_count: int
    started_at: datetime | None
    completed_at: datetime | None
    input_tokens: int
    output_tokens: int
    tool_calls: int | None
    settled_cost_usd: Decimal | None
    validated_output: dict[str, object] | None
    error_code: str | None
    error_summary: str | None
    created_at: datetime


class ModelUsageRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    input_tokens: int
    output_tokens: int
    tool_calls: int | None
    settled_cost_usd: Decimal | None


class RunUsageRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    input_tokens: int
    output_tokens: int
    tool_calls: int | None
    settled_cost_usd: Decimal | None
    models: list[ModelUsageRead]
