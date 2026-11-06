from django.conf import settings

from .dispatchers import CeleryJobDispatcher, JobDispatcher
from .handlers.registry import registry
from .repositories import DjangoJobRepository
from .services.execution_service import JobExecutionService
from .services.retry_policy import RetryPolicy
from .services.submission_service import JobSubmissionService
from .services.sweeper_service import SweeperService


def build_dispatcher() -> JobDispatcher:
    return CeleryJobDispatcher()


def build_submission_service() -> JobSubmissionService:
    return JobSubmissionService(DjangoJobRepository(), build_dispatcher())


def build_execution_service() -> JobExecutionService:
    return JobExecutionService(DjangoJobRepository(), registry, RetryPolicy(), build_dispatcher())


def build_sweeper_service() -> SweeperService:
    return SweeperService(
        DjangoJobRepository(),
        build_dispatcher(),
        timeout_seconds=settings.JOB_TIMEOUT_SECONDS,
        pending_grace_seconds=settings.JOB_PENDING_GRACE_SECONDS,
    )
