# Background Job Processing System

A production-ready background job processing system built with **Django 5.2**, **Django REST Framework**, **Celery 5**, **Redis 7**, and **PostgreSQL 16**.

It supports asynchronous job submission, background execution, lifecycle status tracking (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`), automatic exponential-backoff retries (max 3 attempts), idempotent submission deduplication, atomic execution locking (`lock_token` fencing), and automatic crash recovery (`sweeper`).

---

## Live Deployment

- **Base URL**: `http://84.12.153.173/api/v1`
- **Health Endpoint**: `http://84.12.153.173/api/v1/health/`
- **Jobs Endpoint**: `http://84.12.153.173/api/v1/jobs/`

---

## Quick Start (Local Docker)

```bash
cp .env.example .env
docker compose up --build -d
```

- API is available at `http://localhost:8000/api/v1/`
- Scale workers at any time: `docker compose up -d --scale worker=3`
- Run the full test suite (including PostgreSQL concurrency tests):
  ```bash
  docker compose exec -T web pytest -v
  ```

---

## API Reference & QA Testing Guide

Base Path: `/api/v1` (e.g., `http://84.12.153.173/api/v1` or `http://localhost:8000/api/v1`)

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/health/` | Verify PostgreSQL and Redis broker connectivity | `200 OK`, `503 Service Unavailable` |
| `POST` | `/jobs/` | Submit a new background job | `202 Accepted` (new), `200 OK` (duplicate), `400 Bad Request` |
| `GET` | `/jobs/` | List jobs (supports `?status=` and `?job_type=` filters) | `200 OK` |
| `GET` | `/jobs/{id}/` | Retrieve job status, result, error, and attempt history | `200 OK`, `404 Not Found` |
| `POST` | `/jobs/{id}/retry/` | Manually reset and re-queue a `FAILED` job | `202 Accepted`, `409 Conflict`, `404 Not Found` |

### Optional Headers
- `Idempotency-Key: <unique-string>` — Prevents duplicate job creation on client retries. If omitted, a deterministic SHA-256 key is automatically derived from `job_type + canonical payload`.
- `X-API-Key: <secret>` — Required only when `API_KEY` is configured in `.env`.

---

## QA Request & Response Payloads

### 1. Health Check
**Request:**
```http
GET /api/v1/health/
```
**Expected Response (`200 OK`):**
```json
{
  "database": "ok",
  "broker": "ok"
}
```

---

### 2. Job Type 1: `TEXT_PROCESSING` (Word, Character, Sentence Count & Top Words)

**Request:**
```http
POST /api/v1/jobs/
Content-Type: application/json
Idempotency-Key: qa-text-001
```
```json
{
  "job_type": "TEXT_PROCESSING",
  "payload": {
    "text": "Hello world! Background jobs in Python are fast. Hello again.",
    "top_n": 3
  }
}
```

**Immediate Submission Response (`202 Accepted`):**
```json
{
  "id": "f0e9ce77-6efb-404e-9302-6f8089a7d33d",
  "job_type": "TEXT_PROCESSING",
  "status": "PENDING",
  "attempts": 0,
  "max_attempts": 3,
  "payload": {
    "text": "Hello world! Background jobs in Python are fast. Hello again.",
    "top_n": 3
  },
  "result": null,
  "error_message": null,
  "idempotency_key": "qa-text-001",
  "created_at": "2026-11-06T18:27:50.112000Z",
  "started_at": null,
  "completed_at": null,
  "next_run_at": "2026-11-06T18:27:50.112000Z",
  "attempt_history": []
}
```

**Status Check Response (`GET /api/v1/jobs/f0e9ce77-6efb-404e-9302-6f8089a7d33d/` -> `200 OK`):**
```json
{
  "id": "f0e9ce77-6efb-404e-9302-6f8089a7d33d",
  "job_type": "TEXT_PROCESSING",
  "status": "COMPLETED",
  "attempts": 1,
  "max_attempts": 3,
  "result": {
    "word_count": 10,
    "character_count": 61,
    "character_count_no_spaces": 52,
    "line_count": 1,
    "sentence_count": 3,
    "top_words": [
      { "word": "hello", "count": 2 },
      { "word": "world", "count": 1 },
      { "word": "background", "count": 1 }
    ]
  },
  "error_message": null,
  "attempt_history": [
    {
      "number": 1,
      "started_at": "2026-11-06T18:27:51.004000Z",
      "finished_at": "2026-11-06T18:27:51.019000Z",
      "success": true,
      "error": null
    }
  ]
}
```

---

### 3. Job Type 2: `EMAIL` (Simulated Email Sending)

**Request:**
```http
POST /api/v1/jobs/
Content-Type: application/json
Idempotency-Key: qa-email-001
```
```json
{
  "job_type": "EMAIL",
  "payload": {
    "recipient": "qa.tester@example.com",
    "subject": "Welcome to Background Jobs",
    "body": "Your account has been verified."
  }
}
```

**Completed Result (`GET /api/v1/jobs/{id}/` -> `200 OK`):**
```json
{
  "status": "COMPLETED",
  "attempts": 1,
  "result": {
    "message_id": "sim-8c75895f7a44fde7",
    "recipient": "qa.tester@example.com",
    "subject": "Welcome to Background Jobs",
    "status": "sent (simulated)"
  }
}
```

---

### 4. Job Type 3: `REPORT` (Data Aggregation, Grouping & Optional CSV Generation)

**Request:**
```http
POST /api/v1/jobs/
Content-Type: application/json
Idempotency-Key: qa-report-001
```
```json
{
  "job_type": "REPORT",
  "payload": {
    "records": [
      { "region": "north", "amount": 120.5 },
      { "region": "north", "amount": 79.5 },
      { "region": "south", "amount": 50.0 }
    ],
    "value_field": "amount",
    "group_by": "region",
    "write_csv": true
  }
}
```

**Completed Result (`GET /api/v1/jobs/{id}/` -> `200 OK`):**
```json
{
  "status": "COMPLETED",
  "attempts": 1,
  "result": {
    "total_records": 3,
    "summary": {
      "count": 3,
      "sum": 250.0,
      "avg": 83.33,
      "min": 50.0,
      "max": 120.5
    },
    "by_group": {
      "north": { "count": 2, "sum": 200.0, "avg": 100.0, "min": 79.5, "max": 120.5 },
      "south": { "count": 1, "sum": 50.0, "avg": 50.0, "min": 50.0, "max": 50.0 }
    },
    "csv_path": "/data/reports/report_f906ad9866b7a68a.csv"
  }
}
```

---

## QA Scenarios Checklist

### Scenario A: Duplicate Submission Prevention (Idempotency)
1. Send any `POST /api/v1/jobs/` request above. Observe HTTP `202 Accepted` and note the returned `id`.
2. Re-send the **exact same request** (same `Idempotency-Key` or identical JSON body).
3. **Expected**: HTTP `200 OK` with the **exact same `id`**. No second job row or second worker execution is triggered.

### Scenario B: Filtering & Pagination
```http
GET /api/v1/jobs/?status=COMPLETED&job_type=REPORT&page=1
```

### Scenario C: Input Validation (`400 Bad Request`)
Send an invalid email address or an unsupported `job_type`:
```json
{
  "job_type": "EMAIL",
  "payload": {
    "recipient": "not-an-email",
    "subject": ""
  }
}
```
**Expected**: HTTP `400 Bad Request` with field-level validation errors before anything is stored or queued.

### Scenario D: Automatic Retries & Permanent Failure (Max 3 Attempts)
- **Transient Failures**: When `EMAIL_FAILURE_RATE=1` is set in `.env`, submitting an `EMAIL` job automatically retries with exponential backoff (`~5s`, then `~25s`) up to `max_attempts=3`. After the 3rd failed attempt, `status` becomes `FAILED` and `attempt_history` lists all 3 attempts.
- **Permanent Failures**: Submitting a `REPORT` job where `amount` is a string (`{"records": [{"amount": "invalid"}]}`) fails immediately on Attempt 1 (`status: "FAILED"`) without wasting retries.
- **Manual Retry**: Send `POST /api/v1/jobs/{id}/retry/` on any `FAILED` job to reset `attempts` to `0` and re-queue it (`202 Accepted`). Sending it on a non-failed job returns `409 Conflict`.

---

## Architecture & Design Patterns

- **Strategy + Registry Pattern** (`apps/jobs/handlers/`): Each job type implements `JobHandler` and registers via `@register("TYPE")`. Adding a new job type requires adding a single handler class without modifying views, services, or tasks.
- **Template Method Pattern** (`JobHandler.handle()`): Validates input against each handler's Pydantic `payload_schema` before calling `execute()`.
- **Repository Pattern** (`apps/jobs/repositories/`): `JobRepository` abstracts database operations (`create_pending`, atomic compare-and-set `claim`, `lock_token`-guarded `complete` / `schedule_retry` / `fail`).
- **Service Layer & Dependency Injection** (`apps/jobs/services/`, `container.py`): Business logic is framework-agnostic and wired in `container.py`.
- **Adapter Pattern** (`apps/jobs/dispatchers.py`): `JobDispatcher` decouples services from Celery.

---

## CI/CD Pipeline (GitHub Actions)

`.github/workflows/ci-cd.yml` runs on every push and pull request to `main`:
1. **`test` job**: Spins up PostgreSQL 16 and Redis 7 service containers, runs `python manage.py check`, and executes the full `pytest` suite (unit, integration, and PostgreSQL concurrency tests).
2. **`deploy` job**: On pushes to `main`, if repository secrets `ORACLE_SSH_KEY` (and optional `ORACLE_HOST`, `ORACLE_USER`) are configured in GitHub (`Settings -> Secrets and variables -> Actions`), it SSHes into the Oracle Cloud VM, pulls `main`, and runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
