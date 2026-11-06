from rest_framework import serializers

from ..domain import InvalidPayload, UnknownJobType
from ..handlers.registry import registry
from ..models import Job, JobAttempt


class JobAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobAttempt
        fields = ["number", "started_at", "finished_at", "success", "error"]


class JobSerializer(serializers.ModelSerializer):
    attempt_history = JobAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "job_type", "status", "attempts", "max_attempts", "payload", "result",
            "error_message", "idempotency_key", "created_at", "started_at", "completed_at",
            "next_run_at", "attempt_history",
        ]
        read_only_fields = fields


class JobCreateSerializer(serializers.Serializer):
    job_type = serializers.CharField(max_length=50)
    payload = serializers.DictField()
    idempotency_key = serializers.CharField(max_length=255, required=False, allow_blank=False)

    def validate(self, attrs):
        try:
            registry.get(attrs["job_type"]).validate_payload(attrs["payload"])
        except UnknownJobType:
            raise serializers.ValidationError(
                {"job_type": f"Unsupported job type. Choose one of: {', '.join(registry.types())}"}
            )
        except InvalidPayload as exc:
            raise serializers.ValidationError({"payload": exc.errors})
        return attrs
