import logging
from datetime import timedelta
from enum import Enum
from typing import Callable

from django.utils import timezone

from ..dispatchers import JobDispatcher
from ..handlers.registry import HandlerRegistry
from ..repositories import JobRepository
from .retry_policy import RetryPolicy

logger = logging.getLogger(__name__)


class RunOutcome(str, Enum):
    SKIPPED = "skipped"
    COMPLETED = "completed"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    LOST = "lost"


class JobExecutionService:
    def __init__(
        self,
        repository: JobRepository,
        registry: HandlerRegistry,
        retry_policy: RetryPolicy,
        dispatcher: JobDispatcher,
        clock: Callable = timezone.now,
    ):
        self._repo = repository
        self._registry = registry
        self._retry_policy = retry_policy
        self._dispatcher = dispatcher
        self._clock = clock

    def run(self, job_id) -> RunOutcome:
        job = self._repo.claim(job_id, self._clock())
        if job is None:
            logger.info("job %s not claimable, skipping", job_id)
            return RunOutcome.SKIPPED

        try:
            handler = self._registry.get(job.job_type)
            result = handler.handle(job.payload)
        except Exception as exc:  # noqa: BLE001
            return self._on_failure(job, exc)

        if self._repo.complete(job, result, self._clock()):
            logger.info("job %s completed (attempt %s)", job.id, job.attempts)
            return RunOutcome.COMPLETED
        logger.warning("job %s: lock lost before saving result", job.id)
        return RunOutcome.LOST

    def _on_failure(self, job, exc: Exception) -> RunOutcome:
        error = f"{type(exc).__name__}: {exc}"
        now = self._clock()
        if self._retry_policy.is_retryable(exc) and job.attempts < job.max_attempts:
            delay = self._retry_policy.next_delay(job.attempts)
            next_run_at = now + timedelta(seconds=delay)
            if not self._repo.schedule_retry(job, error, next_run_at, now):
                return RunOutcome.LOST
            logger.warning("job %s attempt %s failed (%s); retry in %.1fs", job.id, job.attempts, error, delay)
            self._dispatcher.enqueue(job.id, countdown=delay)
            return RunOutcome.RETRY_SCHEDULED
        if not self._repo.fail(job, error, now):
            return RunOutcome.LOST
        logger.error("job %s failed permanently after %s attempt(s): %s", job.id, job.attempts, error)
        return RunOutcome.FAILED
