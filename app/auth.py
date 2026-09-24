"""Single-admin login, same approach as Paradise City Music: one username +
password hash from the environment, remembered in Flask's signed session.

Unlike that app, the admin/admin dev fallback only works on SQLite (your
laptop). On Postgres (the droplet) a missing ADMIN_PASSWORD_HASH means
nobody can log in, rather than silently accepting admin/admin on the
public internet.
"""
from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import db

bp = Blueprint("auth", __name__, url_prefix="/admin")

_DEV_HASH = generate_password_hash("admin")


def _password_hash():
    configured = current_app.config.get("ADMIN_PASSWORD_HASH")
    if configured:
        return configured
    if db.engine.dialect.name == "sqlite":
        return _DEV_HASH
    return None


def _current_path():
    # script_root is the /candyshoptiles prefix behind Caddy (empty locally);
    # without it the post-login redirect would land on another app.
    return request.script_root + request.full_path.rstrip("?")


def is_admin():
    return bool(session.get("is_admin"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            return redirect(url_for("auth.login", next=_current_path()))
        return view(*args, **kwargs)

    return wrapped


def require_admin():
    """For `bp.before_request(require_admin)` -- guards a whole blueprint."""
    if not is_admin():
        return redirect(url_for("auth.login", next=_current_path()))


def _safe_next(value):
    # Only ever follow a local path, never an off-site URL.
    if value and value.startswith("/") and not value.startswith(("//", "/\\")):
        return value
    return url_for("admin.dashboard")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if is_admin():
        return redirect(url_for("admin.dashboard"))
    next_url = request.values.get("next") or ""
    password_hash = _password_hash()
    if password_hash is None:
        flash("Admin login is disabled: ADMIN_PASSWORD_HASH isn't set on this server.", "error")

    if request.method == "POST" and password_hash:
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == current_app.config["ADMIN_USERNAME"] and check_password_hash(password_hash, password):
            session["is_admin"] = True
            return redirect(_safe_next(request.form.get("next")))
        flash("Incorrect username or password.", "error")

    return render_template("admin/login.html", next_url=next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("is_admin", None)
    flash("Logged out.", "success")
    return redirect(url_for("main.designer"))
