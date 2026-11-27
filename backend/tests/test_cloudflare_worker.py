"""The Cloudflare Worker serves the same app shell policy as Django does.

cloudflare/src/edge.js sets the headers when Cloudflare serves the PWA;
config/frontend.py sets them when Django does. A change to one must reach the
other, or the two deployments would quietly differ.
"""

import re
from pathlib import Path

import pytest

from config.frontend import CONTENT_SECURITY_POLICY, NO_CACHE

WORKER = Path(__file__).resolve().parents[2] / "cloudflare" / "src" / "edge.js"
pytestmark = pytest.mark.skipif(not WORKER.exists(), reason="no cloudflare/ here")


def worker_source():
    return WORKER.read_text()


def test_the_content_security_policy_is_identical():
    block = re.search(
        r"CONTENT_SECURITY_POLICY = \[(.*?)\]\.join\(\"; \"\)", worker_source(), re.S
    )
    assert block, "CONTENT_SECURITY_POLICY not found in edge.js"
    directives = re.findall(r'"([^"]+)"', block.group(1))
    assert "; ".join(directives) == CONTENT_SECURITY_POLICY


def test_the_same_files_are_always_revalidated():
    block = re.search(r"const NO_CACHE = new Set\(\[(.*?)\]\)", worker_source(), re.S)
    names = {
        path.rsplit("/", 1)[-1] for path in re.findall(r'"([^"]+)"', block.group(1))
    }
    assert names - {""} == NO_CACHE  # "/" is index.html


def test_the_same_names_count_as_content_hashed():
    from config.frontend import HASHED_FRONTEND_ASSET

    match = re.search(r"const HASHED_ASSET = /(.*?)/;", worker_source())
    assert match.group(1).replace("\\/", "/") == HASHED_FRONTEND_ASSET.pattern
