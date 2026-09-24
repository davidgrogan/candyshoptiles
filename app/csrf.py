"""Minimal CSRF protection for every POST -- the public order form, the
share-link API and all admin actions. Forms include
`<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`;
fetch() calls send the same value in an X-CSRF-Token header (read from the
<meta name="csrf-token"> tag in base.html)."""
import hmac
import secrets

from flask import abort, current_app, request, session


def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def _check():
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf") or ""
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="Your session expired -- please go back, reload the page and try again.")


def init_app(app):
    app.before_request(_check)
    app.jinja_env.globals["csrf_token"] = csrf_token
