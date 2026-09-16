"""Optional first-run helper. All application execution goes through Django manage.py."""
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ENV=ROOT/'.venv'
PYTHON=ENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')

def run(*args):
    subprocess.run([str(PYTHON),*args],cwd=ROOT,check=True)

def main():
    if sys.version_info<(3,10): raise SystemExit('Python 3.10 or newer is required.')
    if not PYTHON.exists():
        print('Creating a local Python virtual environment...')
        venv.EnvBuilder(with_pip=True).create(ENV)
    marker=ENV/'.requirements-installed'
    requirements=(ROOT/'requirements.txt').read_text()
    if not marker.exists() or marker.read_text()!=requirements:
        print('Installing Django, Django REST Framework and application dependencies...')
        run('-m','pip','install','-r','requirements.txt')
        marker.write_text(requirements)
    run('manage.py','migrate','--noinput')
    check=subprocess.run([str(PYTHON),'manage.py','shell','-c',
        "from django.contrib.auth import get_user_model; import sys; sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)"],cwd=ROOT)
    if check.returncode==1:
        print('\nCreate your local Django administrator account:')
        run('manage.py','createsuperuser')
    elif check.returncode:
        raise SystemExit('Could not check local users. Review the error above.')
    run('manage.py','seed_demo')
    run('manage.py','runlocal',*sys.argv[1:])

if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError as exc: raise SystemExit(exc.returncode)
    except KeyboardInterrupt: pass
