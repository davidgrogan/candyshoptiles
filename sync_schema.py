"""Add any missing columns / widen any too-narrow ones on the configured
database, without ever dropping or narrowing anything. See
app/schema_sync.py for the details.

On the droplet (deploy_all.sh does this for you):

    set -a; source deploy/candyshoptiles.env; set +a
    python3 sync_schema.py            # dry run: show what would change
    python3 sync_schema.py --apply    # run it

Local SQLite doesn't need this -- create_app() applies the same sync
automatically on every start.
"""
import sys

from app import create_app
from app.models import db
from app.schema_sync import apply, plan


def main():
    app = create_app()  # also runs db.create_all() for brand-new tables
    with app.app_context():
        backend = db.engine.url.get_backend_name()
        steps = plan(db)
        if not steps:
            print(f"Schema is up to date ({backend}) -- nothing to add or widen.")
            return
        print(f"{len(steps)} schema change(s) pending on {backend}:")
        for label, statement in steps:
            print(f"  {label}\n    {statement};")
        if "--apply" not in sys.argv:
            print("\nDry run only. Re-run with --apply to execute.")
            return
        apply(db, steps)
        print("Applied.")


if __name__ == "__main__":
    main()
