import time
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.db import close_old_connections,OperationalError
from cashflows.models import CalculationRun
from cashflows.services import execute_run

class Command(BaseCommand):
    help='Process the durable local Django queue. Use one worker with SQLite; use Celery for PostgreSQL deployments.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true',help='Process at most one queued run, then exit.')
    def handle(self,*args,**options):
        if settings.TASK_BACKEND!='database': raise CommandError('Use a Celery worker when TASK_BACKEND=celery.')
        self.stdout.write('Django calculation worker ready. Ctrl+C to stop.')
        try:
            while True:
                close_old_connections()
                try:
                    run=CalculationRun.objects.filter(status='queued').order_by('created').values_list('pk',flat=True).first()
                    if run:
                        execute_run(run)
                        self.stdout.write(f'Processed {run}')
                    if options['once']: return
                    if not run: time.sleep(.5)
                except OperationalError:
                    if options['once']: raise
                    time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write('Worker stopped. Any interrupted run can be marked using recover_runs.')
        finally: close_old_connections()
