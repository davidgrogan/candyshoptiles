import os

from dotenv import load_dotenv
from flask import Flask, session

from app.models import db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Loads a local .env if present; on the droplet systemd's EnvironmentFile=
# sets these instead and there's no .env to find.
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url and url.startswith("postgres://"):
        # Some hosts hand out the old scheme, which SQLAlchemy rejects.
        url = url.replace("postgres://", "postgresql://", 1)
    if url:
        return url
    path = os.path.join(BASE_DIR, "instance", "candyshoptiles.sqlite3")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return f"sqlite:///{path}"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        # `or`, not .get(key, default): a blank `SECRET_KEY=` line copied
        # from .env.example still counts as set and would break sessions.
        SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-secret-change-me",
        SQLALCHEMY_DATABASE_URI=_database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Distinct cookie name/path so this can't collide with sibling apps
        # on waveyvibe.dev (see deploy/candyshoptiles.env.example).
        SESSION_COOKIE_NAME=os.environ.get("SESSION_COOKIE_NAME") or "candyshoptiles_session",
        SESSION_COOKIE_PATH=os.environ.get("SESSION_COOKIE_PATH") or "/",
        SESSION_COOKIE_SAMESITE="Lax",
        # Whole-request cap; a batch of phone photos in one admin upload.
        MAX_CONTENT_LENGTH=60 * 1024 * 1024,
        UPLOAD_FOLDER=os.path.join(BASE_DIR, "app", "static", "uploads", "art"),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME") or "admin",
        ADMIN_PASSWORD_HASH=os.environ.get("ADMIN_PASSWORD_HASH") or "",
        RESEND_API_KEY=os.environ.get("RESEND_API_KEY") or "",
        RESEND_FROM_EMAIL=os.environ.get("RESEND_FROM_EMAIL") or "Candy Shop Tiles <onboarding@resend.dev>",
        ORDER_NOTIFY_EMAIL=os.environ.get("ORDER_NOTIFY_EMAIL") or "",
        CSRF_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    from app import csrf
    from app.auth import bp as auth_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.main import bp as main_bp
    from app.routes.orders import bp as orders_bp

    csrf.init_app(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    from app import pricing
    from app.images import image_url

    # Globals (not a context processor) so imported macros can use them too.
    app.jinja_env.filters["money"] = pricing.money
    app.jinja_env.globals["prices"] = pricing
    app.jinja_env.globals["image_url"] = image_url

    @app.context_processor
    def inject_is_admin():
        return {"is_admin": bool(session.get("is_admin"))}

    with app.app_context():
        db.create_all()
        if db.engine.dialect.name == "sqlite":
            # Local dev: keep the SQLite file's columns current on every
            # start. Postgres gets the same thing via sync_schema.py --apply
            # in deploy_all.sh -- deliberately not at app start there, so a
            # schema change always happens as a visible deploy step.
            from app.schema_sync import apply, plan

            steps = plan(db)
            if steps:
                apply(db, steps)
                app.logger.warning("Added %d missing column(s) to local SQLite: %s",
                                   len(steps), ", ".join(label for label, _ in steps))

    return app
