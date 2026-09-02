from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, time

import pytest
from pydantic import ValidationError

from competitor_scout.agents.contracts import ScoutPlan
from competitor_scout.agents.orchestrator import (
    MAX_OTARI_TOOL_ITERATIONS,
    PlanValidationError,
    tool_iteration_budget,
    validate_scout_plan,
)
from competitor_scout.jobs.executor import JobExecutor
from competitor_scout.jobs.scheduler import (
    daily_deduplication_key,
    first_valid_local_occurrence,
    weekly_deduplication_key,
)
from competitor_scout.models.jobs import Job, JobStatus


def plan(payload: dict[str, object]) -> ScoutPlan:
    return ScoutPlan.model_validate(payload, strict=False)


def test_plan_cannot_expand_approved_first_party_scope() -> None:
    candidate = plan(
        {
            "tasks": [
                {
                    "kind": "first_party_source_review",
                    "objective": "Review an unapproved page",
                    "source_urls": ["https://other.example/pricing"],
                    "search_query": None,
                    "expected_category": "pricing",
                    "max_search_calls": 1,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        }
    )

    with pytest.raises(PlanValidationError) as raised:
        validate_scout_plan(
            candidate,
            approved_urls={"https://acme.example/pricing"},
            max_tasks=8,
            max_search_calls=2,
        )

    assert raised.value.code == "invalid_plan_scope"


def test_first_party_plan_requires_a_bounded_search_budget() -> None:
    with pytest.raises(ValidationError, match="search budget"):
        plan(
            {
                "tasks": [
                    {
                        "kind": "first_party_source_review",
                        "objective": "Review the approved pricing page",
                        "source_urls": ["https://acme.example/pricing"],
                        "search_query": None,
                        "expected_category": "pricing",
                        "max_search_calls": 0,
                        "completion_criteria": "Return directly quoted evidence or none",
                    }
                ]
            }
        )


def test_plan_cannot_exceed_deployment_search_limit() -> None:
    candidate = plan(
        {
            "tasks": [
                {
                    "kind": "news_discovery",
                    "objective": "Review public reporting",
                    "source_urls": [],
                    "search_query": "Acme product launch",
                    "expected_category": "product",
                    "max_search_calls": 3,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        }
    )

    with pytest.raises(PlanValidationError) as raised:
        validate_scout_plan(
            candidate,
            approved_urls=set(),
            max_tasks=8,
            max_search_calls=2,
        )

    assert raised.value.code == "invalid_plan_limits"


def test_tool_iteration_budget_leaves_headroom_above_the_search_budget() -> None:
    assert tool_iteration_budget(1) > 2
    assert tool_iteration_budget(4) > 5


def test_tool_iteration_budget_stays_within_the_gateway_ceiling() -> None:
    assert tool_iteration_budget(24) == MAX_OTARI_TOOL_ITERATIONS


def test_schedule_keys_are_stable() -> None:
    assert daily_deduplication_key("competitor", date(2026, 10, 25)) == (
        "daily_scout:competitor:2026-10-25"
    )
    assert weekly_deduplication_key("user", date(2026, 10, 25)) == ("weekly_brief:user:2026-10-25")


def test_dst_uses_first_ambiguous_occurrence_and_first_valid_time_after_gap() -> None:
    ambiguous = first_valid_local_occurrence(
        date(2026, 10, 25),
        time(2, 30),
        "Europe/Berlin",
    )
    nonexistent = first_valid_local_occurrence(
        date(2026, 3, 29),
        time(2, 30),
        "Europe/Berlin",
    )

    assert ambiguous.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert ambiguous.fold == 0
    assert nonexistent.hour == 3 and nonexistent.minute == 0


class FakeRepository:
    def __init__(self, job: Job) -> None:
        self.job = job
        self.renewed = asyncio.Event()
        self.completed: list[uuid.UUID] = []
        self.failed: list[tuple[uuid.UUID, str]] = []

    async def claim(self, _owner: str, *, lease_seconds: int) -> Job | None:
        assert lease_seconds == 30
        job, self.job = self.job, None  # type: ignore[assignment]
        return job

    async def renew(self, job_id: uuid.UUID, _owner: str, *, lease_seconds: int) -> Job:
        assert lease_seconds == 30
        self.renewed.set()
        return self.job_for_return(job_id)

    async def complete(self, job_id: uuid.UUID, _owner: str) -> Job:
        self.completed.append(job_id)
        return self.job_for_return(job_id)

    async def fail(
        self,
        job_id: uuid.UUID,
        _owner: str,
        *,
        error_code: str,
    ) -> Job:
        self.failed.append((job_id, error_code))
        return self.job_for_return(job_id)

    @staticmethod
    def job_for_return(job_id: uuid.UUID) -> Job:
        return Job(
            id=job_id,
            job_type="daily_scout",
            deduplication_key="daily:key",
            payload={"run_id": str(uuid.uuid4())},
            status=JobStatus.COMPLETED,
        )


async def test_executor_renews_lease_until_handler_finishes() -> None:
    job = Job(
        id=uuid.uuid4(),
        job_type="daily_scout",
        deduplication_key="daily:key",
        payload={"run_id": str(uuid.uuid4())},
        status=JobStatus.LEASED,
        lease_owner="worker-a",
    )
    repository = FakeRepository(job)
    release = asyncio.Event()

    async def handler(_payload: dict[str, object]) -> None:
        await release.wait()

    executor = JobExecutor(
        repository=repository,  # type: ignore[arg-type]
        handlers={"daily_scout": handler},
        lease_seconds=30,
        renewal_interval_seconds=0.01,
    )
    running = asyncio.create_task(executor.run_once("worker-a"))
    await asyncio.wait_for(repository.renewed.wait(), timeout=1)
    release.set()

    assert await asyncio.wait_for(running, timeout=1) is True
    assert repository.completed == [job.id]
    assert repository.failed == []
