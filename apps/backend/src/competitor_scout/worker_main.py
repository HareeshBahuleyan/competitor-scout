from __future__ import annotations

import asyncio
import signal
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from competitor_scout.agents.client import OtariClient
from competitor_scout.agents.costs import ConfiguredCostEstimator
from competitor_scout.agents.orchestrator import ScoutOrchestrator, SourceDiscoveryService
from competitor_scout.config import Settings, get_settings
from competitor_scout.db import SessionFactory, create_engine, create_session_factory
from competitor_scout.jobs.executor import JobExecutor, JobHandler
from competitor_scout.jobs.handlers import SourceDiscoveryHandler
from competitor_scout.jobs.repository import JobRepository
from competitor_scout.jobs.scheduler import schedule_due_daily_runs, schedule_due_weekly_briefs
from competitor_scout.jobs.weekly_brief import WeeklyBriefHandler
from competitor_scout.security.urls import validate_public_https_url
from competitor_scout.services.findings import FindingPublicationService
from competitor_scout.services.snapshots import SnapshotPublicationService

SCHEDULER_INTERVAL_SECONDS = 30.0
EXECUTOR_IDLE_SECONDS = 1.0
LEASE_SECONDS = 60
LEASE_RENEWAL_SECONDS = 20.0
TERMINATION_GRACE_SECONDS = 25.0


async def scheduler_loop(
    session_factory: SessionFactory,
    stop: asyncio.Event,
    *,
    interval_seconds: float = SCHEDULER_INTERVAL_SECONDS,
) -> None:
    while not stop.is_set():
        now = datetime.now(UTC)
        async with session_factory.begin() as session:
            await schedule_due_daily_runs(
                session,
                now=now,
            )
            await schedule_due_weekly_briefs(session, now=now)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass


def _run_id(payload: dict[str, object]) -> uuid.UUID:
    value = payload.get("run_id")
    if not isinstance(value, str):
        raise ValueError("job payload has no run_id")
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise ValueError("job payload run_id is invalid") from error


def build_handlers(
    *,
    daily_orchestrator: ScoutOrchestrator,
    discovery_handler: SourceDiscoveryHandler,
    weekly_handler: WeeklyBriefHandler,
) -> dict[str, JobHandler]:
    async def daily(payload: dict[str, object]) -> None:
        await daily_orchestrator.execute_daily_run(_run_id(payload))

    async def discovery(payload: dict[str, object]) -> None:
        await discovery_handler.handle(run_id=_run_id(payload))

    async def weekly(payload: dict[str, object]) -> None:
        await weekly_handler.handle(run_id=_run_id(payload))

    return {
        "daily_scout": daily,
        "manual_scout": daily,
        "source_discovery": discovery,
        "weekly_brief": weekly,
    }


@asynccontextmanager
async def worker_resources(
    settings: Settings,
) -> AsyncIterator[tuple[SessionFactory, JobExecutor]]:
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    client = OtariClient(settings)
    publisher = FindingPublicationService(
        sessions,
        minimum_confidence=Decimal(str(settings.finding_confidence_threshold)),
    )
    cost_estimator = ConfiguredCostEstimator(settings)
    daily_orchestrator = ScoutOrchestrator(
        session_factory=sessions,
        client=client,
        settings=settings,
        publisher=publisher,
        snapshot_publisher=SnapshotPublicationService(sessions),
        url_validator=validate_public_https_url,
        cost_estimator=cost_estimator,
    )
    discovery_handler = SourceDiscoveryHandler(
        sessions,
        service=SourceDiscoveryService(
            client=client,
            settings=settings,
            url_validator=validate_public_https_url,
        ),
        settings=settings,
        cost_estimator=cost_estimator,
    )
    weekly_handler = WeeklyBriefHandler(
        sessions,
        client=client,
        settings=settings,
        cost_estimator=cost_estimator,
    )
    repository = JobRepository(sessions)
    executor = JobExecutor(
        repository=repository,
        handlers=build_handlers(
            daily_orchestrator=daily_orchestrator,
            discovery_handler=discovery_handler,
            weekly_handler=weekly_handler,
        ),
        lease_seconds=LEASE_SECONDS,
        renewal_interval_seconds=LEASE_RENEWAL_SECONDS,
    )
    try:
        yield sessions, executor
    finally:
        await client.aclose()
        await engine.dispose()


async def worker_service(settings: Settings | None = None) -> None:
    resolved = settings or get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop.set)
        except NotImplementedError:
            pass

    async with worker_resources(resolved) as (sessions, executor):
        tasks = [asyncio.create_task(scheduler_loop(sessions, stop))]
        executor_count = max(1, min(resolved.max_otari_concurrency, 4))
        tasks.extend(
            asyncio.create_task(
                executor.run_loop(
                    f"worker-{uuid.uuid4()}",
                    stop,
                    idle_seconds=EXECUTOR_IDLE_SECONDS,
                )
            )
            for _ in range(executor_count)
        )
        stop_waiter = asyncio.create_task(stop.wait())
        done, _pending = await asyncio.wait(
            {*tasks, stop_waiter},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for completed in done:
            if completed is not stop_waiter and completed.exception() is not None:
                stop.set()
                break
        if stop_waiter not in done:
            stop.set()
        try:
            async with asyncio.timeout(TERMINATION_GRACE_SECONDS):
                await asyncio.gather(*tasks)
        except TimeoutError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            stop_waiter.cancel()
            await asyncio.gather(stop_waiter, return_exceptions=True)


def run() -> None:
    asyncio.run(worker_service())
