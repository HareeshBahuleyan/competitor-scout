from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from competitor_scout.models.jobs import Job

type JobHandler = Callable[[dict[str, object]], Awaitable[None]]


class JobStore(Protocol):
    async def claim(self, lease_owner: str, *, lease_seconds: int) -> Job | None: ...

    async def renew(
        self,
        job_id,
        lease_owner: str,
        *,
        lease_seconds: int,
    ) -> Job: ...

    async def complete(self, job_id, lease_owner: str) -> Job: ...

    async def fail(
        self,
        job_id,
        lease_owner: str,
        *,
        error_code: str,
    ) -> Job: ...


class JobExecutor:
    def __init__(
        self,
        *,
        repository: JobStore,
        handlers: Mapping[str, JobHandler],
        lease_seconds: int = 60,
        renewal_interval_seconds: float = 20,
    ) -> None:
        if lease_seconds <= 0 or not 0 < renewal_interval_seconds < lease_seconds:
            raise ValueError("lease and renewal intervals are invalid")
        self._repository = repository
        self._handlers = dict(handlers)
        self._lease_seconds = lease_seconds
        self._renewal_interval = renewal_interval_seconds

    async def run_once(self, lease_owner: str) -> bool:
        job = await self._repository.claim(
            lease_owner,
            lease_seconds=self._lease_seconds,
        )
        if job is None:
            return False
        handler = self._handlers.get(job.job_type)
        if handler is None:
            await self._repository.fail(
                job.id,
                lease_owner,
                error_code="unknown_job_type",
            )
            return True

        stop_renewal = asyncio.Event()
        handler_task = asyncio.create_task(handler(job.payload))
        renewal_task = asyncio.create_task(
            self._renew_until_stopped(job, lease_owner, stop_renewal)
        )
        try:
            done, _pending = await asyncio.wait(
                {handler_task, renewal_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if renewal_task in done:
                renewal_task.result()
                raise RuntimeError("lease renewal stopped before handler")
            await handler_task
        except asyncio.CancelledError:
            handler_task.cancel()
            raise
        except Exception as error:
            handler_task.cancel()
            await asyncio.gather(handler_task, return_exceptions=True)
            await self._repository.fail(
                job.id,
                lease_owner,
                error_code=self._safe_error_code(error),
            )
        else:
            await self._repository.complete(job.id, lease_owner)
        finally:
            stop_renewal.set()
            await asyncio.gather(renewal_task, return_exceptions=True)
        return True

    async def run_loop(
        self,
        lease_owner: str,
        stop: asyncio.Event,
        *,
        idle_seconds: float = 1,
    ) -> None:
        while not stop.is_set():
            claimed = await self.run_once(lease_owner)
            if not claimed:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=idle_seconds)
                except TimeoutError:
                    pass

    async def _renew_until_stopped(
        self,
        job: Job,
        lease_owner: str,
        stop: asyncio.Event,
    ) -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._renewal_interval)
                return
            except TimeoutError:
                await self._repository.renew(
                    job.id,
                    lease_owner,
                    lease_seconds=self._lease_seconds,
                )

    @staticmethod
    def _safe_error_code(error: Exception) -> str:
        code = getattr(error, "code", None)
        return code if isinstance(code, str) and len(code) <= 100 else "job_handler_failed"
