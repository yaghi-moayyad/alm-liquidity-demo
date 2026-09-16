from datetime import timedelta
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from cashflows.models import CalculationRun

class Command(BaseCommand):
    help='After stopping stale workers, mark abandoned running jobs interrupted. Creates no replacement jobs.'
    def add_arguments(self,parser):
        parser.add_argument('--minutes',type=int,default=15)
        parser.add_argument('--workers-stopped',action='store_true')
    def handle(self,*args,**options):
        if not options['workers_stopped']: raise CommandError('Stop stale workers first, then supply --workers-stopped.')
        if options['minutes']<1: raise CommandError('--minutes must be at least 1')
        cutoff=timezone.now()-timedelta(minutes=options['minutes'])
        n=CalculationRun.objects.filter(status='running',heartbeat__lt=cutoff).update(status='interrupted',finished=timezone.now(),error='Worker interrupted. Submit a new run using a new idempotency key.')
        self.stdout.write(f'Marked {n} runs interrupted.')
