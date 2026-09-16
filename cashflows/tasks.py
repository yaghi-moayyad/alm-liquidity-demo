from celery import shared_task
from .services import execute_run

@shared_task(ignore_result=True)
def calculate_run(run_id):
    return execute_run(run_id)
