from django.urls import path

from . import views

urlpatterns = [
    path("jobs/", views.JobListCreateView.as_view(), name="job-list-create"),
    path("jobs/<uuid:pk>/", views.JobDetailView.as_view(), name="job-detail"),
    path("jobs/<uuid:pk>/retry/", views.JobRetryView.as_view(), name="job-retry"),
    path("health/", views.HealthView.as_view(), name="health"),
]

