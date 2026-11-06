import hashlib
import random
import time

from django.conf import settings
from pydantic import BaseModel, Field

from ..domain import TransientJobError
from .base import JobHandler
from .registry import register


class EmailPayload(BaseModel):
    recipient: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str = Field(min_length=1, max_length=255)
    body: str = ""


@register("EMAIL")
class EmailHandler(JobHandler):
    payload_schema = EmailPayload

    def execute(self, payload: EmailPayload) -> dict:
        time.sleep(settings.EMAIL_SIMULATED_DELAY)
        if random.random() < settings.EMAIL_FAILURE_RATE:
            raise TransientJobError("Simulated SMTP failure")
        digest = hashlib.sha1(f"{payload.recipient}|{payload.subject}|{payload.body}".encode()).hexdigest()
        return {
            "message_id": f"sim-{digest[:16]}",
            "recipient": payload.recipient,
            "subject": payload.subject,
            "status": "sent (simulated)",
        }
