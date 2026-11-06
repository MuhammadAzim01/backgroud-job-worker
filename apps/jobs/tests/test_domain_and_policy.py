import pytest

from apps.jobs.domain import InvalidTransition, JobStatus, can_transition, ensure_transition
from apps.jobs.services.retry_policy import RetryPolicy
from apps.jobs.domain import PermanentJobError, TransientJobError

pytestmark = pytest.mark.unit

P, R, C, F = JobStatus.PENDING, JobStatus.PROCESSING, JobStatus.COMPLETED, JobStatus.FAILED


def test_legal_transitions():
    assert can_transition(P, R)
    assert can_transition(R, C) and can_transition(R, P) and can_transition(R, F)
    assert can_transition(F, P)


@pytest.mark.parametrize("a,b", [(P, C), (P, F), (C, P), (C, R), (F, R), (F, C)])
def test_illegal_transitions(a, b):
    assert not can_transition(a, b)
    with pytest.raises(InvalidTransition):
        ensure_transition(a, b)


def test_backoff_without_jitter():
    policy = RetryPolicy(jitter=0)
    assert [policy.next_delay(n) for n in (1, 2, 3, 4)] == [5, 25, 125, 125]


def test_backoff_jitter_only_adds():
    policy = RetryPolicy(jitter=0.2, rng=lambda: 1.0)
    assert policy.next_delay(1) == pytest.approx(6.0)


def test_retryable_classification():
    assert RetryPolicy.is_retryable(TransientJobError("x"))
    assert RetryPolicy.is_retryable(RuntimeError("unexpected"))
    assert not RetryPolicy.is_retryable(PermanentJobError("x"))

