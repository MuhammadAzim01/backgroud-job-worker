import hashlib
import json
from typing import Optional

from django.db import transaction
from django.utils import timezone

from ..dispatchers import JobDispatcher
from ..repositories import JobRepository


def derive_idempotency_key(job_type: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "auto:" + hashlib.sha256(f"{job_type}:{canonical}".encode()).hexdigest()


class JobSubmissionService:
    def __init__(self, repository: JobRepository, dispatcher: JobDispatcher):
        self._repo = repository
        self._dispatcher = dispatcher

    def submit(self, job_type: str, payload: dict, idempotency_key: Optional[str] = None):
        key = idempotency_key or derive_idempotency_key(job_type, payload)
        job, created = self._repo.create_pending(job_type, payload, key)
        if created:
            transaction.on_commit(lambda: self._dispatcher.enqueue(job.id))
        return job, created

    def retry(self, job_id) -> bool:
        if not self._repo.requeue_failed(job_id, timezone.now()):
            return False
        transaction.on_commit(lambda: self._dispatcher.enqueue(job_id))
        return True
