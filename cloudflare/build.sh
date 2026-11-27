#!/usr/bin/env bash
# Build the PWA this Worker serves. Wrangler runs it before `deploy` and `dev`.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm ci --include=dev
npm run build
for file in index.html sw.js manifest.webmanifest; do
  test -f "dist/$file" || { echo "build.sh: dist/$file is missing" >&2; exit 1; }
done
