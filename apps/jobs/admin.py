from django.contrib import admin

from .models import Job, JobAttempt


class JobAttemptInline(admin.TabularInline):
    model = JobAttempt
    extra = 0
    readonly_fields = ("number", "started_at", "finished_at", "success", "error")
    can_delete = False


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "job_type", "status", "attempts", "created_at", "completed_at")
    list_filter = ("status", "job_type")
    search_fields = ("id", "idempotency_key")
    readonly_fields = ("id", "created_at", "updated_at", "lock_token")
    inlines = [JobAttemptInline]

