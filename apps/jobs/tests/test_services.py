import pytest
from django.db import IntegrityError, transaction

from apps.jobs.domain import JobStatus
from apps.jobs.models import Job
from apps.jobs.repositories import DjangoJobRepository
from apps.jobs.services.execution_service import JobExecutionService, RunOutcome
from apps.jobs.services.retry_policy import RetryPolicy
from apps.jobs.services.submission_service import JobSubmissionService, derive_idempotency_key
from apps.jobs.services.sweeper_service import SweeperService

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def make_job(job_type="OK", **kw):
    job, _ = DjangoJobRepository().create_pending(job_type, {}, kw.pop("key", f"k-{Job.objects.count()}"))
    return job


def make_exec(registry, dispatcher, clock):
    return JobExecutionService(DjangoJobRepository(), registry, RetryPolicy(jitter=0), dispatcher, clock)


def test_submit_creates_pending_and_enqueues_after_commit(dispatcher, django_capture_on_commit_callbacks):
    svc = JobSubmissionService(DjangoJobRepository(), dispatcher)
    with django_capture_on_commit_callbacks(execute=True):
        job, created = svc.submit("OK", {"a": 1}, "key-1")
        assert dispatcher.calls == []
    assert created and job.status == JobStatus.PENDING.value
    assert dispatcher.calls == [(str(job.id), 0)]


def test_duplicate_submission_returns_same_job_and_enqueues_once(dispatcher, django_capture_on_commit_callbacks):
    svc = JobSubmissionService(DjangoJobRepository(), dispatcher)
    with django_capture_on_commit_callbacks(execute=True):
        first, c1 = svc.submit("OK", {"a": 1}, "same")
        second, c2 = svc.submit("OK", {"a": 2}, "same")
    assert (c1, c2) == (True, False)
    assert first.id == second.id
    assert Job.objects.count() == 1
    assert len(dispatcher.calls) == 1


def test_derived_key_is_stable_and_order_insensitive():
    a = derive_idempotency_key("OK", {"x": 1, "y": 2})
    assert a == derive_idempotency_key("OK", {"y": 2, "x": 1})
    assert a != derive_idempotency_key("OTHER", {"x": 1, "y": 2})


def test_db_constraints_block_bad_attempts():
    job = make_job()
    with pytest.raises(IntegrityError), transaction.atomic():
        Job.objects.filter(pk=job.pk).update(attempts=job.max_attempts + 1)


def test_only_one_claim_wins(clock):
    repo = DjangoJobRepository()
    job = make_job()
    first = repo.claim(job.id, clock())
    second = repo.claim(job.id, clock())
    assert first is not None and first.status == JobStatus.PROCESSING.value and first.attempts == 1
    assert second is None


def test_stale_lock_token_cannot_overwrite(clock):
    repo = DjangoJobRepository()
    job = repo.claim(make_job().id, clock())
    clock.advance(1000)
    repo.reset_stale(job, clock())
    new = repo.claim(job.id, clock())
    assert repo.complete(job, {"stale": True}, clock()) is False
    assert repo.complete(new, {"fresh": True}, clock()) is True
    assert Job.objects.get(pk=job.pk).result == {"fresh": True}


def test_successful_execution(test_registry, dispatcher, clock):
    job = make_job("OK")
    outcome = make_exec(test_registry, dispatcher, clock).run(job.id)
    job.refresh_from_db()
    assert outcome is RunOutcome.COMPLETED
    assert (job.status, job.attempts, job.result) == ("COMPLETED", 1, {"ok": True})
    assert job.attempt_history.get().success is True


def test_redelivered_task_does_not_execute_twice(test_registry, dispatcher, clock):
    job = make_job("OK")
    svc = make_exec(test_registry, dispatcher, clock)
    assert svc.run(job.id) is RunOutcome.COMPLETED
    assert svc.run(job.id) is RunOutcome.SKIPPED
    assert Job.objects.get(pk=job.pk).attempts == 1


def test_transient_failure_retries_then_fails_after_three_attempts(test_registry, dispatcher, clock):
    job = make_job("FLAKY")
    svc = make_exec(test_registry, dispatcher, clock)

    assert svc.run(job.id) is RunOutcome.RETRY_SCHEDULED
    job.refresh_from_db()
    assert (job.status, job.attempts) == ("PENDING", 1)
    assert dispatcher.calls[-1] == (str(job.id), 5.0)
    assert svc.run(job.id) is RunOutcome.SKIPPED

    clock.advance(6)
    assert svc.run(job.id) is RunOutcome.RETRY_SCHEDULED
    assert dispatcher.calls[-1] == (str(job.id), 25.0)

    clock.advance(26)
    assert svc.run(job.id) is RunOutcome.FAILED
    job.refresh_from_db()
    assert (job.status, job.attempts) == ("FAILED", 3)
    assert "boom" in job.error_message
    assert [a.success for a in job.attempt_history.all()] == [False, False, False]

    clock.advance(1000)
    assert svc.run(job.id) is RunOutcome.SKIPPED


def test_permanent_error_fails_immediately(test_registry, dispatcher, clock):
    job = make_job("BAD")
    assert make_exec(test_registry, dispatcher, clock).run(job.id) is RunOutcome.FAILED
    job.refresh_from_db()
    assert (job.status, job.attempts) == ("FAILED", 1)
    assert dispatcher.calls == []


def test_unknown_job_type_fails_without_retry(test_registry, dispatcher, clock):
    job = make_job("DOES_NOT_EXIST")
    assert make_exec(test_registry, dispatcher, clock).run(job.id) is RunOutcome.FAILED


def test_manual_retry_of_failed_job(test_registry, dispatcher, clock, django_capture_on_commit_callbacks):
    job = make_job("BAD")
    make_exec(test_registry, dispatcher, clock).run(job.id)
    sub = JobSubmissionService(DjangoJobRepository(), dispatcher)
    with django_capture_on_commit_callbacks(execute=True):
        assert sub.retry(job.id) is True
    job.refresh_from_db()
    assert (job.status, job.attempts) == ("PENDING", 0)
    assert sub.retry(job.id) is False


def make_sweeper(dispatcher, clock):
    return SweeperService(DjangoJobRepository(), dispatcher, timeout_seconds=300, pending_grace_seconds=60, clock=clock)


def test_sweeper_requeues_abandoned_processing_job(dispatcher, clock):
    repo = DjangoJobRepository()
    job = repo.claim(make_job().id, clock())
    old_token = job.lock_token
    sweeper = make_sweeper(dispatcher, clock)

    assert sweeper.run()["reset"] == 0
    clock.advance(301)
    assert sweeper.run()["reset"] == 1
    job.refresh_from_db()
    assert job.status == "PENDING"
    assert job.lock_token != old_token
    assert dispatcher.calls[-1][0] == str(job.id)


def test_sweeper_fails_abandoned_job_with_exhausted_attempts(dispatcher, clock):
    repo = DjangoJobRepository()
    job = make_job()
    Job.objects.filter(pk=job.pk).update(attempts=2)
    claimed = repo.claim(job.id, clock())
    assert claimed.attempts == 3
    clock.advance(301)
    assert make_sweeper(dispatcher, clock).run()["failed"] == 1
    assert Job.objects.get(pk=job.pk).status == "FAILED"


def test_sweeper_republishes_lost_pending_messages(dispatcher, clock):
    job = make_job()
    clock.advance(61)
    sweeper = make_sweeper(dispatcher, clock)
    assert sweeper.run()["requeued"] == 1
    assert sweeper.run()["requeued"] == 0
    assert dispatcher.calls == [(str(job.id), 0)]


def test_run_sweeper_command_once(monkeypatch, dispatcher):
    from django.core.management import call_command
    from apps.jobs import container

    monkeypatch.setattr(container, "build_dispatcher", lambda: dispatcher)
    call_command("run_sweeper", "--once")
