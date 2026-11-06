import logging
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.jobs import container

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=float,
            default=float(getattr(settings, "JOB_SWEEP_INTERVAL_SECONDS", 15)),
        )
        parser.add_argument(
            "--once",
            action="store_true",
        )

    def handle(self, *args, **options):
        interval = max(options["interval"], 1.0)
        once = options["once"]
        running = True

        def _stop(signum, frame):
            nonlocal running
            running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info("sweeper starting (interval=%.1fs, once=%s)", interval, once)
        while running:
            try:
                close_old_connections()
                container.build_sweeper_service().run()
            except Exception:  # noqa: BLE001
                logger.exception("sweeper pass failed")
            if once:
                break
            deadline = time.monotonic() + interval
            while running and time.monotonic() < deadline:
                time.sleep(min(0.5, deadline - time.monotonic()))
        logger.info("sweeper stopped")
