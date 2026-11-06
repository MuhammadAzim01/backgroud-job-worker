import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import F

from ..domain import JobStatus
from ..models import Job, JobAttempt


class JobRepository(ABC):
    @abstractmethod
    def create_pending(self, job_type: str, payload: dict, idempotency_key: str) -> tuple[Job, bool]: ...

    @abstractmethod
    def get(self, job_id) -> Optional[Job]: ...

    @abstractmethod
    def claim(self, job_id, now: datetime) -> Optional[Job]: ...

    @abstractmethod
    def complete(self, job: Job, result: dict, now: datetime) -> bool: ...

    @abstractmethod
    def schedule_retry(self, job: Job, error: str, next_run_at: datetime, now: datetime) -> bool: ...

    @abstractmethod
    def fail(self, job: Job, error: str, now: datetime) -> bool: ...

    @abstractmethod
    def requeue_failed(self, job_id, now: datetime) -> bool: ...

    @abstractmethod
    def stale_processing(self, started_before: datetime) -> list[Job]: ...

    @abstractmethod
    def reset_stale(self, job: Job, now: datetime) -> Optional[JobStatus]: ...

    @abstractmethod
    def due_pending(self, now: datetime, untouched_since: datetime) -> list[Job]: ...

    @abstractmethod
    def touch(self, job_id, now: datetime) -> None: ...


class DjangoJobRepository(JobRepository):
    def create_pending(self, job_type, payload, idempotency_key):
        try:
            with transaction.atomic():
                job = Job.objects.create(
                    job_type=job_type,
                    payload=payload,
                    idempotency_key=idempotency_key,
                    status=JobStatus.PENDING.value,
                )
            return job, True
        except IntegrityError:
            existing = Job.objects.filter(idempotency_key=idempotency_key).first()
            if existing is None:
                raise
            return existing, False

    def get(self, job_id):
        return Job.objects.filter(pk=job_id).first()

    def claim(self, job_id, now):
        token = uuid.uuid4()
        updated = Job.objects.filter(
            pk=job_id,
            status=JobStatus.PENDING.value,
            next_run_at__lte=now,
            attempts__lt=F("max_attempts"),
        ).update(
            status=JobStatus.PROCESSING.value,
            attempts=F("attempts") + 1,
            lock_token=token,
            started_at=now,
            updated_at=now,
        )
        if not updated:
            return None
        job = Job.objects.get(pk=job_id)
        JobAttempt.objects.create(job=job, number=job.attempts, started_at=now)
        return job

    def _finish_attempt(self, job: Job, now, success: bool, error: Optional[str]):
        JobAttempt.objects.filter(job_id=job.pk, number=job.attempts).update(
            finished_at=now, success=success, error=error
        )

    def _guarded(self, job: Job):
        return Job.objects.filter(pk=job.pk, status=JobStatus.PROCESSING.value, lock_token=job.lock_token)

    def complete(self, job, result, now):
        ok = self._guarded(job).update(
            status=JobStatus.COMPLETED.value,
            result=result,
            error_message=None,
            completed_at=now,
            updated_at=now,
        )
        if ok:
            self._finish_attempt(job, now, True, None)
        return bool(ok)

    def schedule_retry(self, job, error, next_run_at, now):
        ok = self._guarded(job).update(
            status=JobStatus.PENDING.value,
            error_message=error,
            next_run_at=next_run_at,
            updated_at=now,
        )
        if ok:
            self._finish_attempt(job, now, False, error)
        return bool(ok)

    def fail(self, job, error, now):
        ok = self._guarded(job).update(
            status=JobStatus.FAILED.value,
            error_message=error,
            completed_at=now,
            updated_at=now,
        )
        if ok:
            self._finish_attempt(job, now, False, error)
        return bool(ok)

    def requeue_failed(self, job_id, now):
        return bool(
            Job.objects.filter(pk=job_id, status=JobStatus.FAILED.value).update(
                status=JobStatus.PENDING.value,
                attempts=0,
                next_run_at=now,
                completed_at=None,
                lock_token=None,
                updated_at=now,
            )
        )

    def stale_processing(self, started_before):
        return list(Job.objects.filter(status=JobStatus.PROCESSING.value, started_at__lt=started_before))

    def reset_stale(self, job, now):
        guarded = self._guarded(job)
        if job.attempts >= job.max_attempts:
            error = "Worker lost: job timed out and attempts are exhausted"
            if guarded.update(
                status=JobStatus.FAILED.value, error_message=error, completed_at=now, updated_at=now
            ):
                self._finish_attempt(job, now, False, error)
                return JobStatus.FAILED
            return None
        error = "Worker lost: job timed out, re-queued"
        if guarded.update(
            status=JobStatus.PENDING.value,
            error_message=error,
            lock_token=uuid.uuid4(),
            next_run_at=now,
            updated_at=now,
        ):
            self._finish_attempt(job, now, False, error)
            return JobStatus.PENDING
        return None

    def due_pending(self, now, untouched_since):
        return list(
            Job.objects.filter(
                status=JobStatus.PENDING.value,
                next_run_at__lte=now,
                updated_at__lt=untouched_since,
            )
        )

    def touch(self, job_id, now):
        Job.objects.filter(pk=job_id).update(updated_at=now)
