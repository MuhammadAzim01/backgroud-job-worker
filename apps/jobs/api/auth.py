import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasApiKey(BasePermission):
    message = "Invalid or missing API key."

    def has_permission(self, request, view):
        expected = settings.API_KEY
        if not expected:
            return True
        provided = request.headers.get("X-API-Key", "")
        return secrets.compare_digest(provided.encode(), expected.encode())
