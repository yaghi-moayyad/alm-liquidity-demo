import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError

class Command(BaseCommand):
    help='Start Django runserver and the separate local calculation worker.'
    def add_arguments(self,parser):
        parser.add_argument('--port',type=int,default=8000)
        parser.add_argument('--no-browser',action='store_true')
    def handle(self,*args,**options):
        if settings.TASK_BACKEND!='database': raise CommandError('runlocal expects TASK_BACKEND=database.')
        if not settings.DEBUG: raise CommandError('runlocal is for development. Use Gunicorn and Celery for deployment.')
        manage=str(Path(settings.BASE_DIR)/'manage.py')
        children=[]
        try:
            children.append(subprocess.Popen([sys.executable,manage,'runworker']))
            children.append(subprocess.Popen([sys.executable,manage,'runserver',f"127.0.0.1:{options['port']}",'--noreload']))
            self.stdout.write(f"Django UI: http://127.0.0.1:{options['port']}/")
            time.sleep(1)
            if not options['no_browser'] and children[1].poll() is None:
                webbrowser.open(f"http://127.0.0.1:{options['port']}/")
            while all(child.poll() is None for child in children): time.sleep(.4)
            if any(child.returncode not in (None,0) for child in children):
                raise CommandError('A local process exited. Review the error above.')
        except KeyboardInterrupt: pass
        finally:
            for child in children:
                if child.poll() is None: child.terminate()
            for child in children:
                try: child.wait(timeout=5)
                except subprocess.TimeoutExpired: child.kill();child.wait()
