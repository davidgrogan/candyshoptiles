"""Entry point for gunicorn in production (see deploy/candyshoptiles.service).

    gunicorn --workers 2 --bind 127.0.0.1:8010 wsgi:app

run.py stays the local-dev entry point (Flask's built-in server).

Wrapped in ProxyFix because Caddy mounts this app under a path on a shared
domain (waveyvibe.dev/candyshoptiles). Caddy's handle_path strips the
"/candyshoptiles" prefix before proxying, and sends it back in an
X-Forwarded-Prefix header; x_prefix=1 turns that into SCRIPT_NAME so
url_for() and static URLs come out as "/candyshoptiles/..." instead of
root-relative paths that would hit the wrong app. x_proto/x_host make
_external=True URLs (e.g. share links) use https and the real hostname.
"""
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

app = create_app()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
