"""Non-destructive schema sync: bring a live database's tables up to what
app/models.py declares, by ADDING missing columns and WIDENING string
columns -- never dropping, renaming, or narrowing anything.

Why: db.create_all() only creates tables that are missing entirely; it
never adds a new column to a table that already exists. This asks the
database what columns it actually has and generates just the ALTER TABLE
statements needed, so it can't miss anything no matter how long it's been
since the last deploy.

Used two ways:
  - Automatically on every app start when the database is SQLite (local
    dev), from create_app() -- so your laptop's database never goes stale.
  - On the droplet's Postgres via sync_schema.py --apply, which
    deploy_all.sh runs after `git pull` and before restarting the service.

Same rule as Paradise City Music: a new NOT NULL column on an existing
table needs `server_default=` in models.py, not just `default=`.
`default=` is Python-side only and invisible to DDL; without a
server_default, Postgres can't backfill existing rows and the ALTER fails
with NotNullViolation.
"""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn


def find_missing_columns(db):
    """[(table, column, [ddl, ...]), ...] for every declared column the
    live table doesn't have. Foreign-key columns get a second statement
    adding the constraint (Postgres only; SQLite can't ALTER in a
    constraint)."""
    inspector = inspect(db.engine)
    dialect = db.engine.dialect
    missing = []
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # create_all() handles whole new tables
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            coldef = CreateColumn(column).compile(dialect=dialect)
            statements = [f'ALTER TABLE "{table.name}" ADD COLUMN {coldef}']
            if dialect.name != "sqlite":
                for fk in column.foreign_keys:
                    statements.append(
                        f'ALTER TABLE "{table.name}" ADD CONSTRAINT "{table.name}_{column.name}_fkey" '
                        f'FOREIGN KEY ("{column.name}") REFERENCES "{fk.column.table.name}" ("{fk.column.name}")'
                    )
            missing.append((table.name, column.name, statements))
    return missing


def find_type_widenings(db):
    """[(table, column, ddl), ...] for existing VARCHAR(n) columns the
    model now declares wider (longer VARCHAR, or unbounded Text). Only
    ever widens. Skipped on SQLite, which doesn't enforce VARCHAR lengths."""
    if db.engine.dialect.name == "sqlite":
        return []
    inspector = inspect(db.engine)
    widenings = []
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        live = {col["name"]: col["type"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            live_type = live.get(column.name)
            live_len = getattr(live_type, "length", None) if live_type is not None else None
            if live_len is None:
                continue  # new column, already unbounded, or not a string
            model_len = getattr(column.type, "length", None)
            if model_len is not None and model_len <= live_len:
                continue
            new_type = column.type.compile(dialect=db.engine.dialect)
            widenings.append(
                (table.name, column.name, f'ALTER TABLE "{table.name}" ALTER COLUMN "{column.name}" TYPE {new_type}')
            )
    return widenings


def plan(db):
    """All pending statements, as [(label, ddl), ...]."""
    steps = []
    for table, column, statements in find_missing_columns(db):
        steps += [(f"{table}.{column} (add)", s) for s in statements]
    for table, column, statement in find_type_widenings(db):
        steps.append((f"{table}.{column} (widen)", statement))
    return steps


def apply(db, steps):
    with db.engine.begin() as conn:
        for _, statement in steps:
            conn.execute(text(statement))
