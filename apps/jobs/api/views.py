from django.db import connection
from django.http import Http404
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import container
from ..models import Job
from .serializers import JobCreateSerializer, JobSerializer


class JobListCreateView(ListAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        qs = Job.objects.prefetch_related("attempt_history")
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"].upper())
        if params.get("job_type"):
            qs = qs.filter(job_type=params["job_type"].upper())
        return qs

    def post(self, request):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")

        job, created = container.build_submission_service().submit(data["job_type"], data["payload"], key)
        return Response(
            JobSerializer(job).data,
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class JobDetailView(RetrieveAPIView):
    serializer_class = JobSerializer
    queryset = Job.objects.prefetch_related("attempt_history")


class JobRetryView(APIView):
    def post(self, request, pk):
        if not Job.objects.filter(pk=pk).exists():
            raise Http404
        if not container.build_submission_service().retry(pk):
            return Response({"detail": "Only FAILED jobs can be retried."}, status=status.HTTP_409_CONFLICT)
        return Response(JobSerializer(Job.objects.get(pk=pk)).data, status=status.HTTP_202_ACCEPTED)


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {}
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {exc}"
        try:
            from config.celery import app

            app.connection_for_read().ensure_connection(max_retries=1, timeout=2)
            checks["broker"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["broker"] = f"error: {exc}"
        healthy = all(v == "ok" for v in checks.values())
        return Response(checks, status=200 if healthy else 503)
