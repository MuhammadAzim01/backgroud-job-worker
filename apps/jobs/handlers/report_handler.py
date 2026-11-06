import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from django.conf import settings
from pydantic import BaseModel, Field

from ..domain import PermanentJobError
from .base import JobHandler
from .registry import register


class ReportPayload(BaseModel):
    records: list[dict] = Field(min_length=1)
    value_field: str = "amount"
    group_by: Optional[str] = None
    write_csv: bool = False


def _stats(values: list[float]) -> dict:
    return {
        "count": len(values),
        "sum": round(sum(values), 2),
        "avg": round(sum(values) / len(values), 2),
        "min": min(values),
        "max": max(values),
    }


@register("REPORT")
class ReportHandler(JobHandler):
    payload_schema = ReportPayload

    def execute(self, payload: ReportPayload) -> dict:
        values = []
        groups: dict[str, list[float]] = defaultdict(list)
        for i, row in enumerate(payload.records):
            value = row.get(payload.value_field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PermanentJobError(f"Record {i}: {payload.value_field!r} must be a number, got {value!r}")
            values.append(value)
            if payload.group_by:
                groups[str(row.get(payload.group_by, "unknown"))].append(value)

        report = {"total_records": len(payload.records), "summary": _stats(values)}
        if payload.group_by:
            report["by_group"] = {k: _stats(v) for k, v in sorted(groups.items())}
        if payload.write_csv:
            report["csv_path"] = self._write_csv(payload)
        return report

    def _write_csv(self, payload: ReportPayload) -> str:
        out_dir = Path(settings.REPORT_OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha1(json.dumps(payload.model_dump(), sort_keys=True).encode()).hexdigest()[:16]
        path = out_dir / f"report_{name}.csv"
        columns = sorted({k for row in payload.records for k in row})
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            writer.writerows(payload.records)
        return str(path)
