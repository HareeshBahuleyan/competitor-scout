from __future__ import annotations

import asyncio
import uuid

import pytest

from competitor_scout.jobs.executor import JobExecutor
from competitor_scout.models.jobs import Job, JobStatus


def job(job_type: str = "daily_scout") -> Job:
    return Job(
        id=uuid.uuid4(),
        job_type=job_type,
        deduplication_key=f"test:{uuid.uuid4()}",
        payload={"run_id": str(uuid.uuid4())},
        status=JobStatus.LEASED,
        lease_owner="worker-a",
    )


class FakeStore:
    def __init__(self, jobs: list[Job] | None = None) -> None:
        self.jobs = list(jobs or [])
        self.completed: list[uuid.UUID] = []
        self.failed: list[tuple[uuid.UUID, str]] = []
        self.renewed = 0

    async def claim(self, _owner: str, *, lease_seconds: int) -> Job | None:
        assert lease_seconds == 30
        return self.jobs.pop(0) if self.jobs else None

    async def renew(self, queued_id, _owner: str, *, lease_seconds: int) -> Job:
        assert lease_seconds == 30
        self.renewed += 1
        return job_for_return(queued_id)

    async def complete(self, queued_id, _owner: str) -> Job:
        self.completed.append(queued_id)
        return job_for_return(queued_id)

    async def fail(self, queued_id, _owner: str, *, error_code: str) -> Job:
        self.failed.append((queued_id, error_code))
        return job_for_return(queued_id)


def job_for_return(job_id: uuid.UUID) -> Job:
    completed = job()
    completed.id = job_id
    completed.status = JobStatus.COMPLETED
    return completed


@pytest.mark.parametrize(
    ("lease_seconds", "renewal_seconds"),
    [(0, 1), (30, 0), (30, 30), (30, 31)],
)
def test_executor_rejects_invalid_lease_intervals(
    lease_seconds: int,
    renewal_seconds: float,
) -> None:
    with pytest.raises(ValueError, match="intervals"):
        JobExecutor(
            repository=FakeStore(),
            handlers={},
            lease_seconds=lease_seconds,
            renewal_interval_seconds=renewal_seconds,
        )


async def test_executor_returns_false_when_no_job_is_available() -> None:
    executor = JobExecutor(
        repository=FakeStore(),
        handlers={},
        lease_seconds=30,
        renewal_interval_seconds=1,
    )

    assert await executor.run_once("worker-a") is False


async def test_executor_fails_unknown_job_type_without_running_handler() -> None:
    queued = job("unknown")
    store = FakeStore([queued])
    executor = JobExecutor(
        repository=store,
        handlers={},
        lease_seconds=30,
        renewal_interval_seconds=1,
    )

    assert await executor.run_once("worker-a") is True
    assert store.failed == [(queued.id, "unknown_job_type")]


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (RuntimeError("provider secret must not escape"), "job_handler_failed"),
        (type("CodedError", (RuntimeError,), {"code": "retryable_failure"})(), "retryable_failure"),
        (type("LongCodeError", (RuntimeError,), {"code": "x" * 101})(), "job_handler_failed"),
    ],
)
async def test_executor_safely_fails_handler_errors(
    error: Exception,
    expected_code: str,
) -> None:
    queued = job()
    store = FakeStore([queued])

    async def failing_handler(_payload: dict[str, object]) -> None:
        raise error

    executor = JobExecutor(
        repository=store,
        handlers={queued.job_type: failing_handler},
        lease_seconds=30,
        renewal_interval_seconds=1,
    )

    assert await executor.run_once("worker-a") is True
    assert store.failed == [(queued.id, expected_code)]
    assert store.completed == []


async def test_executor_fails_if_renewal_stops_before_handler(monkeypatch) -> None:
    queued = job()
    store = FakeStore([queued])
    handler_started = asyncio.Event()

    async def waiting_handler(_payload: dict[str, object]) -> None:
        handler_started.set()
        await asyncio.Event().wait()

    executor = JobExecutor(
        repository=store,
        handlers={queued.job_type: waiting_handler},
        lease_seconds=30,
        renewal_interval_seconds=1,
    )

    async def stopped_renewal(*_args) -> None:
        return None

    monkeypatch.setattr(executor, "_renew_until_stopped", stopped_renewal)

    assert await executor.run_once("worker-a") is True
    assert handler_started.is_set()
    assert store.failed == [(queued.id, "job_handler_failed")]


async def test_executor_cancellation_cancels_handler() -> None:
    queued = job()
    store = FakeStore([queued])
    handler_started = asyncio.Event()
    handler_cancelled = asyncio.Event()

    async def waiting_handler(_payload: dict[str, object]) -> None:
        handler_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            handler_cancelled.set()

    executor = JobExecutor(
        repository=store,
        handlers={queued.job_type: waiting_handler},
        lease_seconds=30,
        renewal_interval_seconds=1,
    )
    running = asyncio.create_task(executor.run_once("worker-a"))
    await asyncio.wait_for(handler_started.wait(), timeout=1)
    running.cancel()

    with pytest.raises(asyncio.CancelledError):
        await running
    await asyncio.wait_for(handler_cancelled.wait(), timeout=1)
    assert store.failed == [] and store.completed == []


async def test_executor_run_loop_waits_when_idle_until_stopped() -> None:
    store = FakeStore()
    executor = JobExecutor(
        repository=store,
        handlers={},
        lease_seconds=30,
        renewal_interval_seconds=1,
    )
    stop = asyncio.Event()
    running = asyncio.create_task(executor.run_loop("worker-a", stop, idle_seconds=0.001))
    await asyncio.sleep(0.005)
    stop.set()

    await asyncio.wait_for(running, timeout=1)
