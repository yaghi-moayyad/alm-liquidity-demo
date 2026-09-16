"""Generate local integration secrets without overwriting an existing .env."""
from pathlib import Path
import secrets
path=Path(__file__).resolve().parent/'.env'
try:
    with path.open('x') as f:
        for key in ('DJANGO_SECRET_KEY','POSTGRES_PASSWORD','RABBITMQ_PASSWORD'):
            f.write(f'{key}={secrets.token_urlsafe(48)}\n')
    path.chmod(0o600)
except FileExistsError:
    raise SystemExit('.env already exists; it was not changed.')
print('Created .env. You can now run: docker compose up --build')
