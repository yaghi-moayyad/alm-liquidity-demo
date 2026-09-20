"""One-click local launcher for the Liquidity MVP.

Creates the Python environment, installs backend dependencies when needed,
builds the React frontend when source files change, applies migrations, seeds
the demo safely, and starts Django plus the local calculation worker.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / '.venv'
PYTHON = ENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
FRONTEND = ROOT / 'frontend'
STATIC_APP = ROOT / 'static' / 'app'


def run(*args, cwd=ROOT):
    subprocess.run([str(PYTHON), *args], cwd=cwd, check=True)


def digest_files(paths):
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p)):
        if not path.is_file():
            continue
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def frontend_source_hash():
    files = [
        FRONTEND / 'package.json', FRONTEND / 'package-lock.json',
        FRONTEND / 'tsconfig.json', FRONTEND / 'vite.config.ts',
        FRONTEND / 'index.html',
    ]
    files += list((FRONTEND / 'src').rglob('*')) if (FRONTEND / 'src').exists() else []
    return digest_files(files)


def prepare_frontend():
    if not (FRONTEND / 'package.json').exists():
        return
    source_hash = frontend_source_hash()
    build_marker = STATIC_APP / '.source-hash'
    manifest = STATIC_APP / '.vite' / 'manifest.json'
    if manifest.exists() and build_marker.exists() and build_marker.read_text().strip() == source_hash:
        print('Frontend build is up to date.')
        return

    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm') or shutil.which('npm')
    if not npm:
        raise SystemExit('Node.js/npm is required to build the updated React frontend. Install Node.js 22 LTS, then run this launcher again.')

    lock = FRONTEND / 'package-lock.json'
    lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else ''
    npm_marker = FRONTEND / 'node_modules' / '.liquidity-lock-hash'
    if not (FRONTEND / 'node_modules').exists() or not npm_marker.exists() or npm_marker.read_text().strip() != lock_hash:
        print('Installing React frontend dependencies...')
        command = [npm, 'ci', '--no-audit', '--no-fund'] if lock.exists() else [npm, 'install', '--no-audit', '--no-fund']
        subprocess.run(command, cwd=FRONTEND, check=True)
        npm_marker.parent.mkdir(parents=True, exist_ok=True)
        npm_marker.write_text(lock_hash)

    print('Building the React frontend...')
    subprocess.run([npm, 'run', 'build'], cwd=FRONTEND, check=True)
    STATIC_APP.mkdir(parents=True, exist_ok=True)
    build_marker.write_text(source_hash)


def main():
    if sys.version_info < (3, 10):
        raise SystemExit('Python 3.10 or newer is required.')
    if not PYTHON.exists():
        print('Creating a local Python virtual environment...')
        venv.EnvBuilder(with_pip=True).create(ENV)

    marker = ENV / '.requirements-installed'
    requirements = (ROOT / 'requirements.txt').read_text()
    if not marker.exists() or marker.read_text() != requirements:
        print('Installing Django, Django REST Framework and application dependencies...')
        run('-m', 'pip', 'install', '-r', 'requirements.txt')
        marker.write_text(requirements)

    prepare_frontend()

    print('Applying database migrations...')
    run('manage.py', 'migrate', '--noinput')
    check = subprocess.run([
        str(PYTHON), 'manage.py', 'shell', '-c',
        "from django.contrib.auth import get_user_model; import sys; sys.exit(0 if get_user_model().objects.filter(is_superuser=True).exists() else 1)"
    ], cwd=ROOT)
    if check.returncode == 1:
        print('\nCreate your local Django administrator account:')
        run('manage.py', 'createsuperuser')
    elif check.returncode:
        raise SystemExit('Could not check local users. Review the error above.')

    print('Checking demo data...')
    run('manage.py', 'seed_demo')
    print('Starting Liquidity MVP...')
    run('manage.py', 'runlocal', *sys.argv[1:])


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
    except KeyboardInterrupt:
        pass
