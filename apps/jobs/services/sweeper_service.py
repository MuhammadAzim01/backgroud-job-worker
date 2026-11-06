import logging
from datetime import timedelta
from typing import Callable

from django.utils import timezone

from ..dispatchers import JobDispatcher
from ..domain import JobStatus
from ..repositories import JobRepository

logger = logging.getLogger(__name__)


class SweeperService:
    def __init__(
        self,
        repository: JobRepository,
        dispatcher: JobDispatcher,
        timeout_seconds: int,
        pending_grace_seconds: int,
        clock: Callable = timezone.now,
    ):
        self._repo = repository
        self._dispatcher = dispatcher
        self._timeout = timedelta(seconds=timeout_seconds)
        self._grace = timedelta(seconds=pending_grace_seconds)
        self._clock = clock

    def run(self) -> dict:
        now = self._clock()
        counts = {"reset": 0, "failed": 0, "requeued": 0}

        for job in self._repo.stale_processing(now - self._timeout):
            outcome = self._repo.reset_stale(job, now)
            if outcome is JobStatus.PENDING:
                counts["reset"] += 1
                self._dispatcher.enqueue(job.id)
            elif outcome is JobStatus.FAILED:
                counts["failed"] += 1

        for job in self._repo.due_pending(now, untouched_since=now - self._grace):
            self._repo.touch(job.id, now)
            self._dispatcher.enqueue(job.id)
            counts["requeued"] += 1

        if any(counts.values()):
            logger.warning("sweeper: %s", counts)
        return counts
