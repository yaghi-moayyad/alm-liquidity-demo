from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from cashflows.models import CalculationRun
from cashflows.services import dispatch_run

class Command(BaseCommand):
    help='Republish queued runs to Celery after restoring the broker. Duplicate deliveries cannot claim an already running/completed run.'
    def handle(self,*args,**options):
        if settings.TASK_BACKEND!='celery': raise CommandError('This command requires TASK_BACKEND=celery.')
        for run_id in CalculationRun.objects.filter(status='queued').values_list('id',flat=True).iterator():
            dispatch_run(run_id)
            self.stdout.write(f'Dispatch attempted: {run_id}')
