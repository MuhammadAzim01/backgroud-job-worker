from enum import Enum


class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @classmethod
    def choices(cls):
        return [(s.value, s.name.title()) for s in cls]


ALLOWED_TRANSITIONS = {
    JobStatus.PENDING: {JobStatus.PROCESSING},
    JobStatus.PROCESSING: {JobStatus.COMPLETED, JobStatus.PENDING, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: {JobStatus.PENDING},
}


class JobError(Exception):
    pass


class InvalidTransition(JobError):
    pass


class TransientJobError(JobError):
    pass


class PermanentJobError(JobError):
    pass


class UnknownJobType(PermanentJobError):
    pass


class InvalidPayload(PermanentJobError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"Invalid payload: {errors}")


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[JobStatus(current)]


def ensure_transition(current: JobStatus, target: JobStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(f"Illegal job transition {current} -> {target}")
