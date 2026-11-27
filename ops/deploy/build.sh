#!/usr/bin/env bash
# Build CharityOS for production: Python packages, the PWA (frontend/dist) and
# the admin's static files (backend/staticfiles).
#
# Render runs this from the repository root as the web service's buildCommand
# (render.yaml). It never connects to the database. Locally:
#   ops/deploy/build.sh            (inside the virtualenv you deploy with)
set -euo pipefail
cd "$(dirname "$0")/../.."

python -m pip install --no-cache-dir -r backend/requirements.txt
npm --prefix frontend ci --include=dev --no-audit --no-fund
npm --prefix frontend run build

# collectstatic imports production settings, which refuse to load without a
# secret key and a host name. The real values are not needed to copy files, so
# placeholders are used only when the build environment has none.
placeholder_key="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
DJANGO_SETTINGS_MODULE=config.settings.production \
DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-$placeholder_key}" \
DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-build.invalid}" \
  python backend/manage.py collectstatic --noinput

test -f frontend/dist/index.html
test -f frontend/dist/sw.js
test -f frontend/dist/manifest.webmanifest
echo "build: frontend/dist and backend/staticfiles are ready."
