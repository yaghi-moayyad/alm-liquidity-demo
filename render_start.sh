#!/usr/bin/env bash
set -euo pipefail

python manage.py migrate --noinput
python manage.py seed_demo --username demo --create-user
# Deliberate review account requested for senior-management demonstration.
# It is idempotent and may be removed from Django admin after approval.
python manage.py seed_demo --username osama --password osama1234 --create-user
# Temporary full-access management review account. Remove before bank-data onboarding.
python manage.py seed_demo --username adel --password adel1234 --create-user
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 120
