from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone

from apps.jobs.models import Job
from apps.jobs.repositories import DjangoJobRepository
from apps.jobs.services.execution_service import JobExecutionService, RunOutcome
from apps.jobs.services.retry_policy import RetryPolicy
from apps.jobs.services.submission_service import JobSubmissionService

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="requires PostgreSQL"),
]


def _in_thread(fn):
    def wrapper(*a):
        try:
            return fn(*a)
        finally:
            close_old_connections()
            connection.close()
    return wrapper


def test_50_parallel_identical_submissions_create_one_job(dispatcher):
    svc = JobSubmissionService(DjangoJobRepository(), dispatcher)

    @_in_thread
    def submit(_):
        return svc.submit("OK", {"same": "payload"})[1]

    with ThreadPoolExecutor(max_workers=20) as pool:
        created_flags = list(pool.map(submit, range(50)))

    assert sum(created_flags) == 1
    assert Job.objects.count() == 1


def test_parallel_claims_have_exactly_one_winner():
    repo = DjangoJobRepository()
    job, _ = repo.create_pending("OK", {}, "claim-race")

    @_in_thread
    def claim(_):
        return repo.claim(job.id, timezone.now()) is not None

    with ThreadPoolExecutor(max_workers=20) as pool:
        wins = list(pool.map(claim, range(20)))

    assert sum(wins) == 1
    assert Job.objects.get(pk=job.pk).attempts == 1


def test_100_jobs_across_workers_none_lost_none_duplicated(test_registry, dispatcher):
    repo = DjangoJobRepository()
    ids = [repo.create_pending("OK", {}, f"bulk-{i}")[0].id for i in range(100)]
    executed = []

    @_in_thread
    def worker(job_id):
        svc = JobExecutionService(DjangoJobRepository(), test_registry, RetryPolicy(), dispatcher)
        return [svc.run(job_id) for _ in range(3)]

    with ThreadPoolExecutor(max_workers=10) as pool:
        for outcomes in pool.map(worker, ids):
            executed.append(outcomes.count(RunOutcome.COMPLETED))

    assert all(n == 1 for n in executed)
    assert Job.objects.filter(status="COMPLETED", attempts=1).count() == 100
