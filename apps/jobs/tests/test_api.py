import uuid

import pytest
from rest_framework.test import APIClient

from apps.jobs import dispatchers
from apps.jobs.models import Job

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

URL = "/api/v1/jobs/"


@pytest.fixture
def client(monkeypatch, dispatcher):
    monkeypatch.setattr(dispatchers.CeleryJobDispatcher, "enqueue", lambda self, job_id, countdown=0: dispatcher.enqueue(job_id, countdown))
    return APIClient()


def post(client, body, **headers):
    return client.post(URL, body, format="json", **headers)


def test_submit_returns_202_and_enqueues(client, dispatcher, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        res = post(client, {"job_type": "TEXT_PROCESSING", "payload": {"text": "hello world"}})
    assert res.status_code == 202
    assert res.data["status"] == "PENDING"
    assert dispatcher.calls == [(res.data["id"], 0)]


def test_duplicate_submission_returns_200_same_job(client, django_capture_on_commit_callbacks):
    body = {"job_type": "TEXT_PROCESSING", "payload": {"text": "hello"}}
    with django_capture_on_commit_callbacks(execute=True):
        a = post(client, body, HTTP_IDEMPOTENCY_KEY="abc")
        b = post(client, body, HTTP_IDEMPOTENCY_KEY="abc")
    assert (a.status_code, b.status_code) == (202, 200)
    assert a.data["id"] == b.data["id"]
    assert Job.objects.count() == 1


def test_identical_requests_without_key_are_deduplicated(client, django_capture_on_commit_callbacks):
    body = {"job_type": "TEXT_PROCESSING", "payload": {"text": "same"}}
    with django_capture_on_commit_callbacks(execute=True):
        statuses = [post(client, body).status_code for _ in range(3)]
    assert statuses == [202, 200, 200]


def test_invalid_payload_is_rejected_before_queueing(client, dispatcher):
    res = post(client, {"job_type": "EMAIL", "payload": {"recipient": "bad"}})
    assert res.status_code == 400
    assert "payload" in res.data
    assert Job.objects.count() == 0 and dispatcher.calls == []


def test_unknown_job_type_rejected(client):
    res = post(client, {"job_type": "NOPE", "payload": {}})
    assert res.status_code == 400 and "job_type" in res.data


def test_get_detail_and_list_filters(client):
    created = post(client, {"job_type": "TEXT_PROCESSING", "payload": {"text": "x"}}).data
    assert client.get(f"{URL}{created['id']}/").data["status"] == "PENDING"
    assert client.get(f"{URL}{uuid.uuid4()}/").status_code == 404
    assert client.get(URL, {"status": "pending"}).data["count"] == 1
    assert client.get(URL, {"status": "completed"}).data["count"] == 0
    assert client.get(URL, {"job_type": "email"}).data["count"] == 0


def test_retry_endpoint_only_for_failed(client):
    created = post(client, {"job_type": "TEXT_PROCESSING", "payload": {"text": "x"}}).data
    assert client.post(f"{URL}{created['id']}/retry/").status_code == 409
    Job.objects.filter(pk=created["id"]).update(status="FAILED")
    assert client.post(f"{URL}{created['id']}/retry/").status_code == 202


def test_api_key_enforced_when_configured(client, settings):
    settings.API_KEY = "secret"
    body = {"job_type": "TEXT_PROCESSING", "payload": {"text": "x"}}
    assert post(client, body).status_code == 403
    assert post(client, body, HTTP_X_API_KEY="wrong").status_code == 403
    assert post(client, body, HTTP_X_API_KEY="secret").status_code == 202
    assert client.get("/api/v1/health/").status_code in (200, 503)


def test_end_to_end_with_real_execution(client, django_capture_on_commit_callbacks):
    from apps.jobs import container

    with django_capture_on_commit_callbacks(execute=False):
        job_id = post(client, {"job_type": "TEXT_PROCESSING", "payload": {"text": "one two two"}}).data["id"]
    assert container.build_execution_service().run(job_id).value == "completed"
    data = client.get(f"{URL}{job_id}/").data
    assert data["status"] == "COMPLETED"
    assert data["result"]["word_count"] == 3
    assert data["attempt_history"][0]["success"] is True
