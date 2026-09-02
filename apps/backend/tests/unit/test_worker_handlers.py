import asyncio
import uuid
from contextlib import asynccontextmanager

from competitor_scout.worker_main import build_handlers, scheduler_loop


class Recorder:
    def __init__(self) -> None:
        self.run_ids: list[uuid.UUID] = []

    async def execute_daily_run(self, run_id: uuid.UUID) -> None:
        self.run_ids.append(run_id)

    async def handle(self, *, run_id: uuid.UUID) -> None:
        self.run_ids.append(run_id)


class NotificationRecorder:
    def __init__(self) -> None:
        self.outbox_ids: list[uuid.UUID] = []

    async def handle(self, *, outbox_id: uuid.UUID) -> None:
        self.outbox_ids.append(outbox_id)


async def test_worker_registers_weekly_brief_handler() -> None:
    run_id = uuid.uuid4()
    daily = Recorder()
    discovery = Recorder()
    weekly = Recorder()
    notifications = NotificationRecorder()
    handlers = build_handlers(
        daily_orchestrator=daily,  # type: ignore[arg-type]
        discovery_handler=discovery,  # type: ignore[arg-type]
        weekly_handler=weekly,  # type: ignore[arg-type]
        notification_handler=notifications,  # type: ignore[arg-type]
    )

    await handlers["weekly_brief"]({"run_id": str(run_id)})
    await handlers["email_notification"]({"outbox_id": str(run_id)})

    assert weekly.run_ids == [run_id]
    assert notifications.outbox_ids == [run_id]
    assert set(handlers) == {
        "daily_scout",
        "manual_scout",
        "source_discovery",
        "weekly_brief",
        "email_notification",
    }


async def test_scheduler_loop_schedules_daily_and_weekly_work_each_tick(monkeypatch) -> None:
    calls: list[str] = []

    class Sessions:
        @asynccontextmanager
        async def begin(self):
            yield object()

    stop = asyncio.Event()

    async def schedule_daily(_session, *, now) -> None:
        assert now.tzinfo is not None
        calls.append("daily")
        stop.set()

    async def schedule_weekly(_session, *, now) -> None:
        assert now.tzinfo is not None
        calls.append("weekly")

    monkeypatch.setattr("competitor_scout.worker_main.schedule_due_daily_runs", schedule_daily)
    monkeypatch.setattr(
        "competitor_scout.worker_main.schedule_due_weekly_briefs",
        schedule_weekly,
        raising=False,
    )

    await scheduler_loop(Sessions(), stop)  # type: ignore[arg-type]

    assert calls == ["daily", "weekly"]
