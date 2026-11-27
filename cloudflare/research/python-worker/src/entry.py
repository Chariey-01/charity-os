"""Probe: the real CharityOS Django project inside a Python Worker."""
import asyncio
import os

from workers import Response, WorkerEntrypoint, env, wsgi

# Hyperdrive's details may only be read inside a handler, so Django starts
# with a placeholder and the real values are applied on the first request.
os.environ["DATABASE_URL"] = "postgresql://placeholder@hyperdrive.invalid/placeholder"
os.environ["DJANGO_SETTINGS_MODULE"] = "cfprobe_settings"
os.environ["DJANGO_SECRET_KEY"] = str(env.DJANGO_SECRET_KEY)
os.environ["DJANGO_ALLOWED_HOSTS"] = str(env.DJANGO_ALLOWED_HOSTS)
os.environ["DJANGO_CSRF_TRUSTED_ORIGINS"] = str(env.DJANGO_CSRF_TRUSTED_ORIGINS)
os.environ["CHARITYOS_FRONTEND_DIST"] = "/nonexistent"
os.environ["CHARITYOS_DB_CONN_MAX_AGE"] = "0"
# Django runs synchronously inside the async handler; _django_lock makes sure
# only one request uses the isolate's connection at a time.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
_db_ready = False
_django_lock = asyncio.Lock()


def _use_hyperdrive(binding):
    global _db_ready
    if _db_ready:
        return
    from django.db import connections

    real = {
        "HOST": str(binding.host),
        "PORT": str(binding.port),
        "USER": str(binding.user),
        "PASSWORD": str(binding.password),
        "NAME": str(binding.database),
    }
    connections.settings["default"].update(real)
    connections["default"].settings_dict.update(real)
    _db_ready = True


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        async with _django_lock:
            return await self._handle(request)

    async def _handle(self, request):
        _use_hyperdrive(self.env.HYPERDRIVE)
        path = request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        if path == "__probe/noop":
            return Response("noop")
        if path == "__probe/pbkdf2":
            from django.contrib.auth.hashers import make_password

            return Response(make_password("probe-password-not-real")[:22])
        if path == "__probe/mem":
            import pyodide_js

            heap = pyodide_js._module.HEAP8.length
            return Response(f"wasm linear memory {heap / 1048576:.1f} MiB")
        if path == "__probe/connect":
            from django.db import connection

            connection.ensure_connection()
            connection.close()
            return Response("connected and closed")
        if path == "__probe/connect2q":
            from django.db import connection

            with connection.cursor() as cur:
                cur.execute("SELECT 1")
                cur.execute("SELECT 1")
            connection.close()
            return Response("2 queries")
        if path == "__probe/migrate":
            import io

            from django.core.management import call_command

            out = io.StringIO()
            call_command("migrate", interactive=False, stdout=out, verbosity=1)
            return Response(out.getvalue()[-3000:])
        return await wsgi.fetch(application, request, self.env)
