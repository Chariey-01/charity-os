#!/usr/bin/env bash
# Copy CharityOS's Django apps into src/ so the probe Worker runs the real code.
# The copies are git-ignored; backend/ stays the only source.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
backend="$here/../../../backend"
for app in api challenges config execution health planning records reflections roadmaps scheduling users; do
  rm -rf "$here/src/$app"
  rsync -a --exclude __pycache__ --exclude tests "$backend/$app" "$here/src/"
done
