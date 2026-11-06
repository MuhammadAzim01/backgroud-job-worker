from abc import ABC, abstractmethod


class JobDispatcher(ABC):
    @abstractmethod
    def enqueue(self, job_id, countdown: float = 0) -> None: ...


class CeleryJobDispatcher(JobDispatcher):
    def enqueue(self, job_id, countdown: float = 0) -> None:
        from .tasks.job_tasks import execute_job

        execute_job.apply_async(args=[str(job_id)], countdown=max(countdown, 0))
