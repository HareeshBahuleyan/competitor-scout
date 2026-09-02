from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.jobs.repository import enqueue_in_session
from competitor_scout.models.intelligence import (
    AgentTask,
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    Finding,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    UsageEvent,
)
from competitor_scout.schemas.runs import (
    ModelUsageRead,
    RunRead,
    RunUsageRead,
    TaskRead,
)

ACTIVE_RUN_STATUSES = (
    ScoutRunStatus.QUEUED,
    ScoutRunStatus.PLANNING,
    ScoutRunStatus.GATHERING,
    ScoutRunStatus.SYNTHESIZING,
)
MANUAL_IDEMPOTENCY_WINDOW = timedelta(minutes=5)
_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,99}$")
_FORBIDDEN_OUTPUT_KEY_PARTS = (
    "authorization",
    "api_key",
    "exception",
    "error_summary",
    "pricing_source",
    "prompt",
    "provider",
    "raw_",
    "request_id",
    "secret",
    "token",
    "traceback",
    "user_id",
)
_OUTPUT_KEYS_BY_TASK_KIND = {
    "daily_planning": frozenset({"tasks"}),
    "daily_synthesis": frozenset({"findings"}),
    "first_party_source_review": frozenset({"sources_inspected", "evidence", "rejected_reasons"}),
    "news_discovery": frozenset({"sources_inspected", "evidence", "rejected_reasons"}),
    "source_discovery": frozenset({"sources", "rejected_count"}),
    "weekly_brief": frozenset({"title", "executive_summary", "sections"}),
}
_RUN_SUMMARIES = {
    "competitor_inactive": "Competitor monitoring is not active.",
    "daily_cost_limit": "The daily usage limit was reached.",
    "main_input_token_limit": "The scan input exceeded its configured limit.",
    "no_valid_evidence": "No valid evidence was available for this scan.",
    "otari_budget_exceeded": "The configured Otari budget was reached.",
    "otari_tool_iteration_limit": "Source discovery exhausted its web search budget.",
    "planning_timeout": "Scan planning timed out.",
    "publication_failed": "Validated updates could not be published.",
    "run_cost_limit": "The scan usage limit was reached.",
    "synthesis_timeout": "Update synthesis timed out.",
}
_PARTIAL_SUMMARIES = {
    "child_task_failed": "Some research tasks could not complete.",
    "cost_ceiling_reached": "The scan stopped before exceeding a usage limit.",
    "insufficient_sources": "No usable sources were discovered.",
    "otari_budget_exceeded": "The scan stopped after reaching the configured Otari budget.",
    "run_cost_limit": "The scan usage limit was reached.",
}
_TASK_SUMMARIES = {
    "child_input_token_limit": "The task input exceeded its configured limit.",
    "child_task_failed": "The research task could not complete.",
    "child_timeout": "The research task timed out.",
    "cost_ceiling_reached": "The task was cancelled before exceeding a usage limit.",
    "main_input_token_limit": "The task input exceeded its configured limit.",
    "otari_budget_exceeded": "The configured Otari budget was reached.",
    "otari_tool_iteration_limit": "The task exhausted its web search budget.",
    "planning_timeout": "Scan planning timed out.",
    "run_cost_limit": "The task was cancelled after reaching a usage limit.",
    "synthesis_timeout": "Update synthesis timed out.",
}


class RunNotFound(ValueError):
    pass


class ManualRunNotAllowed(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


def _current_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("run clock must be timezone-aware")
    return value.astimezone(UTC)


def _encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    payload = json.dumps(
        [created_at.astimezone(UTC).isoformat(), str(record_id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(decoded, list) or len(decoded) != 2:
            raise ValueError
        created_at = datetime.fromisoformat(decoded[0])
        if created_at.tzinfo is None:
            raise ValueError
        return created_at.astimezone(UTC), uuid.UUID(decoded[1])
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error


def _safe_code(value: object) -> str | None:
    return value if isinstance(value, str) and _SAFE_CODE.fullmatch(value) else None


def _contains_sensitive_marker(value: str) -> bool:
    normalized = value.casefold().replace("-", "_").replace(" ", "_")
    return any(part in normalized for part in _FORBIDDEN_OUTPUT_KEY_PARTS)


def _safe_objective(task: AgentTask) -> str:
    value = " ".join(task.objective.split())
    if value and len(value) <= 500 and not _contains_sensitive_marker(value):
        return value
    return task.task_kind.replace("_", " ").strip().capitalize() or "Agent task"


def _safe_source_scope(task: AgentTask) -> list[str]:
    safe: list[str] = []
    for item in task.source_scope[:100]:
        if not isinstance(item, str) or len(item) > 2048 or _contains_sensitive_marker(item):
            continue
        if item.startswith("search:"):
            safe.append(item)
            continue
        parsed = urlsplit(item)
        if (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
        ):
            safe.append(item)
    return safe


def _safe_json(value: object, *, depth: int = 0) -> object | None:
    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [
            safe for item in value[:100] if (safe := _safe_json(item, depth=depth + 1)) is not None
        ]
    if isinstance(value, dict):
        output: dict[str, object] = {}
        for key, item in list(value.items())[:100]:
            if not isinstance(key, str):
                continue
            normalized = key.casefold()
            if any(part in normalized for part in _FORBIDDEN_OUTPUT_KEY_PARTS):
                continue
            safe = _safe_json(item, depth=depth + 1)
            if safe is not None:
                output[key] = safe
        return output
    return None


def safe_task_output(task: AgentTask) -> dict[str, object] | None:
    allowed = _OUTPUT_KEYS_BY_TASK_KIND.get(task.task_kind)
    if allowed is None or not isinstance(task.validated_output, dict):
        return None
    selected = {key: value for key, value in task.validated_output.items() if key in allowed}
    rejected_reasons = selected.get("rejected_reasons")
    if isinstance(rejected_reasons, list):
        selected["rejected_reasons"] = [
            code for item in rejected_reasons if (code := _safe_code(item)) is not None
        ]
    safe = _safe_json(selected)
    return safe if isinstance(safe, dict) else None


def run_read(
    run: ScoutRun,
    *,
    competitor_name: str | None = None,
    finding_count: int = 0,
) -> RunRead:
    partial_reasons = [
        code for item in run.partial_reasons if (code := _safe_code(item)) is not None
    ]
    return RunRead(
        id=run.id,
        competitor_id=run.competitor_id,
        competitor_name=competitor_name,
        finding_count=finding_count,
        run_type=run.run_type,
        status=run.status,
        scheduled_for=run.scheduled_for,
        started_at=run.started_at,
        completed_at=run.completed_at,
        failure_code=_safe_code(run.failure_code),
        failure_summary=_RUN_SUMMARIES.get(_safe_code(run.failure_code) or ""),
        partial_reasons=partial_reasons,
        partial_summaries=[
            summary for code in partial_reasons if (summary := _PARTIAL_SUMMARIES.get(code))
        ],
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        tool_calls=run.tool_calls,
        settled_cost_usd=run.settled_cost_usd,
        created_at=run.created_at,
    )


def task_read(task: AgentTask) -> TaskRead:
    return TaskRead(
        id=task.id,
        scout_run_id=task.scout_run_id,
        parent_task_id=task.parent_task_id,
        role=task.role,
        task_kind=task.task_kind,
        status=task.status,
        model=task.model,
        objective=_safe_objective(task),
        source_scope=_safe_source_scope(task),
        attempt_count=task.attempt_count,
        started_at=task.started_at,
        completed_at=task.completed_at,
        input_tokens=task.input_tokens,
        output_tokens=task.output_tokens,
        tool_calls=task.tool_calls,
        settled_cost_usd=task.settled_cost_usd,
        validated_output=safe_task_output(task),
        error_code=_safe_code(task.error_code),
        error_summary=_TASK_SUMMARIES.get(_safe_code(task.error_code) or ""),
        created_at=task.created_at,
    )


async def enqueue_manual_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    competitor_id: uuid.UUID,
    now: datetime,
) -> ScoutRun:
    current = _current_time(now)
    lock_key = f"manual_scout:{user_id}:{competitor_id}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )
    competitor = await session.scalar(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == user_id,
            Competitor.status != CompetitorStatus.DELETED,
        )
    )
    if competitor is None:
        raise RunNotFound("competitor was not found")
    if competitor.status is not CompetitorStatus.ACTIVE:
        raise ManualRunNotAllowed("competitor_inactive")
    approved_source = await session.scalar(
        select(MonitoredSource.id).where(
            MonitoredSource.competitor_id == competitor.id,
            MonitoredSource.approval_status == ApprovalStatus.APPROVED,
        )
    )
    if approved_source is None:
        raise ManualRunNotAllowed("approved_source_required")

    active = await session.scalar(
        select(ScoutRun)
        .where(
            ScoutRun.user_id == user_id,
            ScoutRun.competitor_id == competitor.id,
            ScoutRun.run_type.in_([RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT]),
            ScoutRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        .order_by(ScoutRun.created_at.desc(), ScoutRun.id.desc())
        .limit(1)
    )
    if active is not None:
        if active.run_type is RunType.MANUAL_SCOUT and active.status is ScoutRunStatus.QUEUED:
            await _enqueue_run_job(session, active, available_at=active.scheduled_for)
        return active

    recent = await session.scalar(
        select(ScoutRun)
        .where(
            ScoutRun.user_id == user_id,
            ScoutRun.competitor_id == competitor.id,
            ScoutRun.run_type == RunType.MANUAL_SCOUT,
            ScoutRun.scheduled_for > current - MANUAL_IDEMPOTENCY_WINDOW,
            ScoutRun.scheduled_for <= current,
        )
        .order_by(ScoutRun.scheduled_for.desc(), ScoutRun.id.desc())
        .limit(1)
    )
    if recent is not None:
        return recent

    statement = (
        insert(ScoutRun)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            competitor_id=competitor.id,
            run_type=RunType.MANUAL_SCOUT,
            status=ScoutRunStatus.QUEUED,
            scheduled_for=current,
        )
        .on_conflict_do_nothing()
        .returning(ScoutRun)
    )
    run = (await session.scalars(statement)).one_or_none()
    if run is None:
        run = await session.scalar(
            select(ScoutRun)
            .where(
                ScoutRun.user_id == user_id,
                ScoutRun.competitor_id == competitor.id,
                ScoutRun.run_type.in_([RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT]),
                ScoutRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .order_by(ScoutRun.created_at.desc(), ScoutRun.id.desc())
            .limit(1)
        )
    if run is None:
        raise RuntimeError("idempotent manual run did not resolve a run")
    await _enqueue_run_job(session, run, available_at=current)
    return run


async def _enqueue_run_job(
    session: AsyncSession,
    run: ScoutRun,
    *,
    available_at: datetime,
) -> None:
    job_type = "manual_scout" if run.run_type is RunType.MANUAL_SCOUT else "daily_scout"
    await enqueue_in_session(
        session,
        job_type,
        f"{job_type}:{run.id}",
        {"run_id": str(run.id)},
        available_at=available_at,
    )


async def list_runs(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    cursor: str | None,
    competitor_id: uuid.UUID | None,
    status: ScoutRunStatus | None,
    run_type: RunType | None,
) -> Page[RunRead]:
    finding_counts = (
        select(
            Finding.originating_scout_run_id.label("run_id"),
            func.count(Finding.id).label("finding_count"),
        )
        .where(Finding.user_id == user_id)
        .group_by(Finding.originating_scout_run_id)
        .subquery()
    )
    statement = (
        select(
            ScoutRun,
            Competitor.name.label("competitor_name"),
            func.coalesce(finding_counts.c.finding_count, 0).label("finding_count"),
        )
        .outerjoin(
            Competitor,
            (Competitor.id == ScoutRun.competitor_id) & (Competitor.user_id == user_id),
        )
        .outerjoin(finding_counts, finding_counts.c.run_id == ScoutRun.id)
        .where(ScoutRun.user_id == user_id)
    )
    if competitor_id is not None:
        statement = statement.where(ScoutRun.competitor_id == competitor_id)
    if status is not None:
        statement = statement.where(ScoutRun.status == status)
    if run_type is not None:
        statement = statement.where(ScoutRun.run_type == run_type)
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                ScoutRun.created_at < created_at,
                (ScoutRun.created_at == created_at) & (ScoutRun.id < record_id),
            )
        )
    records = list(
        (
            await session.execute(
                statement.order_by(ScoutRun.created_at.desc(), ScoutRun.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(records) > limit
    visible = records[:limit]
    return Page(
        items=[
            run_read(run, competitor_name=competitor_name, finding_count=finding_count)
            for run, competitor_name, finding_count in visible
        ],
        next_cursor=(
            _encode_cursor(visible[-1][0].created_at, visible[-1][0].id) if has_more else None
        ),
    )


async def run_summary(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
) -> RunRead | None:
    finding_count = (
        select(func.count(Finding.id))
        .where(
            Finding.originating_scout_run_id == ScoutRun.id,
            Finding.user_id == user_id,
        )
        .correlate(ScoutRun)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(
                ScoutRun,
                Competitor.name.label("competitor_name"),
                finding_count.label("finding_count"),
            )
            .outerjoin(
                Competitor,
                (Competitor.id == ScoutRun.competitor_id) & (Competitor.user_id == user_id),
            )
            .where(ScoutRun.id == run_id, ScoutRun.user_id == user_id)
        )
    ).one_or_none()
    if row is None:
        return None
    run, competitor_name, count = row
    return run_read(run, competitor_name=competitor_name, finding_count=count)


async def owned_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
) -> ScoutRun | None:
    return await session.scalar(
        select(ScoutRun).where(ScoutRun.id == run_id, ScoutRun.user_id == user_id)
    )


async def list_run_tasks(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> Page[TaskRead]:
    statement = select(AgentTask).where(AgentTask.scout_run_id == run_id)
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                AgentTask.created_at > created_at,
                (AgentTask.created_at == created_at) & (AgentTask.id > record_id),
            )
        )
    records = list(
        (
            await session.scalars(
                statement.order_by(AgentTask.created_at, AgentTask.id).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(records) > limit
    visible = records[:limit]
    return Page(
        items=[task_read(task) for task in visible],
        next_cursor=(_encode_cursor(visible[-1].created_at, visible[-1].id) if has_more else None),
    )


@dataclass
class _UsageGroup:
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    settled_cost_usd: Decimal = Decimal("0")
    tool_calls_known: bool = True
    cost_known: bool = True

    def add(self, event: UsageEvent) -> None:
        self.input_tokens += event.input_tokens
        self.output_tokens += event.output_tokens
        if event.tool_calls is None:
            self.tool_calls_known = False
        elif self.tool_calls_known:
            self.tool_calls += event.tool_calls
        if event.settled_cost_usd is None:
            self.cost_known = False
        elif self.cost_known:
            self.settled_cost_usd += event.settled_cost_usd

    def read(self, model: str) -> ModelUsageRead:
        return ModelUsageRead(
            model=model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            tool_calls=self.tool_calls if self.tool_calls_known else None,
            settled_cost_usd=(self.settled_cost_usd if self.cost_known else None),
        )


async def run_usage(session: AsyncSession, run: ScoutRun) -> RunUsageRead:
    events = list(
        (
            await session.scalars(
                select(UsageEvent)
                .where(UsageEvent.scout_run_id == run.id)
                .order_by(UsageEvent.occurred_at, UsageEvent.id)
            )
        ).all()
    )
    groups: dict[str, _UsageGroup] = {}
    for event in events:
        groups.setdefault(event.model, _UsageGroup()).add(event)
    return RunUsageRead(
        run_id=run.id,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        tool_calls=run.tool_calls,
        settled_cost_usd=run.settled_cost_usd,
        models=[groups[model].read(model) for model in sorted(groups)],
    )
