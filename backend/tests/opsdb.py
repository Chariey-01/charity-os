"""Helpers shared by the ops/db script tests."""

import os
import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

REPO_ROOT = Path(settings.BASE_DIR).parent
OPS = REPO_ROOT / "ops" / "db"


def run(script, *args, env=None):
    return subprocess.run(
        [str(OPS / script), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
        timeout=300,
    )


def result_value(result, key):
    """The ``KEY=value`` a script prints as its last line."""
    return result.stdout.strip().splitlines()[-1].removeprefix(f"{key}=")


def major(tool):
    if not shutil.which(tool):
        return 0
    output = subprocess.run([tool, "--version"], capture_output=True, text=True)
    return int(re.search(r"(\d+)\.", output.stdout).group(1))


def psql(env, sql):
    return subprocess.run(
        ["psql", "-X", "-At", "-d", "postgres", "-c", sql],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        check=True,
    ).stdout.strip()
