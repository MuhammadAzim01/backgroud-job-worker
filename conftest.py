from datetime import datetime, timedelta, timezone

import pytest

from apps.jobs.dispatchers import JobDispatcher
from apps.jobs.domain import PermanentJobError, TransientJobError
from apps.jobs.handlers.base import JobHandler
from apps.jobs.handlers.registry import HandlerRegistry


class FakeDispatcher(JobDispatcher):
    def __init__(self):
        self.calls = []

    def enqueue(self, job_id, countdown=0):
        self.calls.append((str(job_id), countdown))


class FakeClock:
    def __init__(self):
        self.now = datetime.now(timezone.utc) + timedelta(seconds=5)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def dispatcher():
    return FakeDispatcher()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def test_registry():
    from pydantic import BaseModel

    class Empty(BaseModel):
        pass

    reg = HandlerRegistry()

    @reg.register("OK")
    class Ok(JobHandler):
        payload_schema = Empty

        def execute(self, payload):
            return {"ok": True}

    @reg.register("FLAKY")
    class Flaky(JobHandler):
        payload_schema = Empty

        def execute(self, payload):
            raise TransientJobError("boom")

    @reg.register("BAD")
    class Bad(JobHandler):
        payload_schema = Empty

        def execute(self, payload):
            raise PermanentJobError("never going to work")

    return reg


@pytest.fixture(autouse=True)
def _fast_handlers(settings, tmp_path):
    settings.EMAIL_SIMULATED_DELAY = 0
    settings.EMAIL_FAILURE_RATE = 0
    settings.REPORT_OUTPUT_DIR = str(tmp_path / "reports")
    settings.API_KEY = ""
