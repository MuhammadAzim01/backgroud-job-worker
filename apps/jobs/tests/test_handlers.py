import csv

import pytest

from apps.jobs.domain import InvalidPayload, PermanentJobError, TransientJobError, UnknownJobType
from apps.jobs.handlers.registry import HandlerRegistry, registry

pytestmark = pytest.mark.unit


def test_registry_has_builtin_handlers():
    assert registry.types() == ["EMAIL", "REPORT", "TEXT_PROCESSING"]


def test_registry_unknown_type():
    with pytest.raises(UnknownJobType):
        registry.get("NOPE")


def test_registry_rejects_duplicates():
    reg = HandlerRegistry()
    reg.register("X")(type("H", (), {}))
    with pytest.raises(ValueError):
        reg.register("X")(type("H2", (), {}))


def test_text_handler():
    out = registry.get("TEXT_PROCESSING").handle({"text": "Hello world. Hello again!", "top_n": 1})
    assert out["word_count"] == 4
    assert out["character_count"] == 25
    assert out["sentence_count"] == 2
    assert out["top_words"] == [{"word": "hello", "count": 2}]


def test_text_handler_invalid_payload():
    with pytest.raises(InvalidPayload):
        registry.get("TEXT_PROCESSING").handle({"text": ""})


def test_email_handler_success_is_deterministic():
    payload = {"recipient": "a@b.com", "subject": "Hi", "body": "x"}
    h = registry.get("EMAIL")
    assert h.handle(payload) == h.handle(payload)
    assert h.handle(payload)["status"].startswith("sent")


def test_email_handler_rejects_bad_address():
    with pytest.raises(InvalidPayload):
        registry.get("EMAIL").handle({"recipient": "nope", "subject": "Hi"})


def test_email_handler_simulated_failure_is_transient(settings):
    settings.EMAIL_FAILURE_RATE = 1.0
    with pytest.raises(TransientJobError):
        registry.get("EMAIL").handle({"recipient": "a@b.com", "subject": "Hi"})


def test_report_handler_aggregates_and_groups():
    records = [
        {"region": "n", "amount": 10},
        {"region": "n", "amount": 20},
        {"region": "s", "amount": 5.5},
    ]
    out = registry.get("REPORT").handle({"records": records, "group_by": "region"})
    assert out["total_records"] == 3
    assert out["summary"]["sum"] == 35.5
    assert out["by_group"]["n"]["avg"] == 15


def test_report_handler_non_numeric_is_permanent():
    with pytest.raises(PermanentJobError):
        registry.get("REPORT").handle({"records": [{"amount": "x"}]})


def test_report_handler_writes_csv():
    out = registry.get("REPORT").handle({"records": [{"amount": 1}, {"amount": 2}], "write_csv": True})
    with open(out["csv_path"], newline="") as fh:
        assert list(csv.DictReader(fh)) == [{"amount": "1"}, {"amount": "2"}]

