from celery import shared_task

from .. import container


@shared_task(name="jobs.execute_job")
def execute_job(job_id: str) -> str:
    return container.build_execution_service().run(job_id).value


@shared_task(name="jobs.sweep_stale_jobs")
def sweep_stale_jobs() -> dict:
    return container.build_sweeper_service().run()
