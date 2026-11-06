import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .domain import JobStatus


def default_max_attempts() -> int:
    return settings.JOB_MAX_ATTEMPTS


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_type = models.CharField(max_length=50)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=JobStatus.choices(), default=JobStatus.PENDING.value)
    idempotency_key = models.CharField(max_length=255, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=default_max_attempts)
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    lock_token = models.UUIDField(null=True, blank=True)
    next_run_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_run_at", "created_at"], name="job_discovery_idx"),
            models.Index(fields=["job_type"], name="job_type_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(attempts__gte=0), name="job_attempts_gte_0"),
            models.CheckConstraint(condition=Q(max_attempts__gte=1), name="job_max_attempts_gte_1"),
            models.CheckConstraint(condition=Q(attempts__lte=F("max_attempts")), name="job_attempts_lte_max"),
        ]

    def __str__(self):
        return f"{self.job_type}:{self.id} [{self.status}]"


class JobAttempt(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="attempt_history")
    number = models.PositiveIntegerField()
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["job", "number"], name="job_attempt_unique_number"),
        ]
