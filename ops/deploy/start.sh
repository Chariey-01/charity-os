#!/usr/bin/env bash
# Start CharityOS in production: gunicorn serving the API, the admin and the
# built PWA (WhiteNoise). Render runs this as the web service's startCommand.
set -euo pipefail
if [[ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings.production" ]]; then
  echo "start: DJANGO_SETTINGS_MODULE must be config.settings.production" >&2
  exit 1
fi
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here/../../backend"
exec gunicorn config.wsgi --config "$here/gunicorn.conf.py"
