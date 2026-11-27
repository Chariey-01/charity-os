"""Gunicorn settings for production (ops/deploy/start.sh)."""

import os

# The platform routes HTTPS traffic to $PORT (Render: 10000 by default).
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
# Two sync workers fit a 512 MB instance with room to spare.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
timeout = 30
graceful_timeout = 25
# Replace workers now and then, so a slow leak can never exhaust memory.
max_requests = 1000
max_requests_jitter = 100
# Heartbeat files in memory, not on a possibly slow container disk.
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None

# Logs go to stdout/stderr, which the platform collects. The access line has
# the path without its query string, the status, size and time in ms.
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(B)s %(M)sms'
