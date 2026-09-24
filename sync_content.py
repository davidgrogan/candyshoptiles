"""Copy your local CONTENT (tile images, categories, sample sets) from the
local SQLite database into the droplet's Postgres, replacing what's there.

Run by deploy_all.sh through its SSH tunnel; you can also run it yourself:

    ssh -L 5434:localhost:5432 root@YOUR_DROPLET_IP -N     # in one tab
    .venv/bin/python sync_content.py "postgresql://candyshoptiles:PW@localhost:5434/candyshoptiles"

What it touches is decided by each table's sync marker in app/models.py:

  content  -- replaced wholesale with your local copy (after you type "yes")
  customer -- NEVER read, wiped or written. Orders and shared designs only
              exist on the live site; your laptop's copies are test data.

Differences from Paradise City Music's migrate_to_postgres.py, both fixing
bugs that script actually hit:
  - The table list and copy order come from the models (dependency-sorted
    by SQLAlchemy), not a hand-kept list -- that list went stale three
    times there, silently skipping new tables. Here an unmarked table is a
    hard error instead.
  - It truncates only the content tables, WITHOUT CASCADE, so Postgres
    itself refuses if anything outside that set ever references them,
    rather than quietly emptying it too.

Columns are copied by name where both sides have them, so a column that
exists on only one side (e.g. local SQLite hasn't been started since a
model change) is reported rather than crashing the copy.
"""
import os
import sys

from sqlalchemy import MetaData, create_engine, func, insert, inspect, select, text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "instance", "candyshoptiles.sqlite3")


def classify_tables():
    """(content_tables_in_dependency_order, customer_table_names). Raises
    if any table lacks a sync marker."""
    from app.models import db

    tables = db.metadata.sorted_tables
    unmarked = [t.name for t in tables if t.info.get("sync") not in ("content", "customer")]
    if unmarked:
        raise SystemExit(
            "These tables have no sync marker in app/models.py: " + ", ".join(unmarked) + "\n"
            "Add info=CONTENT or info=CUSTOMER to each (see the docstring at the top of app/models.py)."
        )
    content = [t.name for t in tables if t.info["sync"] == "content"]
    customer = [t.name for t in tables if t.info["sync"] == "customer"]
    return content, customer


def _count(conn, table):
    return conn.execute(select(func.count()).select_from(table)).scalar()


def summarize(src_engine, dst_engine, content, customer):
    src_meta, dst_meta = MetaData(), MetaData()
    src_meta.reflect(bind=src_engine, only=content)
    dst_meta.reflect(bind=dst_engine, only=[t for t in content + customer if inspect(dst_engine).has_table(t)])
    missing = [t for t in content if t not in dst_meta.tables]
    lines = []
    with src_engine.connect() as s, dst_engine.connect() as d:
        for name in content:
            here = _count(s, src_meta.tables[name])
            there = _count(d, dst_meta.tables[name]) if name in dst_meta.tables else "missing"
            lines.append(f"  {name:<20} laptop {here:>5}   ->  droplet now {there:>5}  (will be replaced)")
        for name in customer:
            there = _count(d, dst_meta.tables[name]) if name in dst_meta.tables else "missing"
            lines.append(f"  {name:<20} {'':>12}       droplet has {there:>5}  (left untouched)")
    return lines, missing, src_meta, dst_meta


def copy_content(src_engine, dst_engine, content, src_meta, dst_meta, log=print):
    is_pg = dst_engine.dialect.name == "postgresql"
    with dst_engine.begin() as dst, src_engine.connect() as src:
        if is_pg:
            names = ", ".join(f'"{n}"' for n in content)
            dst.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY"))
        else:  # SQLite target (tests)
            for n in reversed(content):
                dst.execute(text(f'DELETE FROM "{n}"'))

        for name in content:
            s_tab, d_tab = src_meta.tables[name], dst_meta.tables[name]
            shared = [c.name for c in d_tab.columns if c.name in s_tab.columns]
            only_dst = [c.name for c in d_tab.columns if c.name not in s_tab.columns]
            only_src = [c.name for c in s_tab.columns if c.name not in d_tab.columns]
            rows = [dict(r._mapping) for r in src.execute(select(*[s_tab.c[c] for c in shared]))]
            if rows:
                dst.execute(insert(d_tab), rows)
            note = ""
            if only_dst:
                note += f"  (not on laptop, left at defaults: {', '.join(only_dst)})"
            if only_src:
                note += f"  (not on droplet, skipped: {', '.join(only_src)})"
            log(f"  {name}: copied {len(rows)} row(s){note}")

        if is_pg:
            for name in content:
                if "id" in dst_meta.tables[name].columns:
                    dst.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('\"{name}\"', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM \"{name}\"), 1), "
                        f"(SELECT MAX(id) FROM \"{name}\") IS NOT NULL)"
                    ))


def main():
    if len(sys.argv) != 2:
        print('Usage: python sync_content.py "postgresql://user:pass@host:port/dbname"')
        sys.exit(1)
    target_url = sys.argv[1]
    if not os.path.exists(SQLITE_PATH):
        print(f"No local database at {SQLITE_PATH} -- nothing to copy. (Run the app or seed.py first.)")
        sys.exit(1)

    content, customer = classify_tables()
    src_engine = create_engine(f"sqlite:///{SQLITE_PATH}")
    dst_engine = create_engine(target_url)

    print(f"From (laptop):  {SQLITE_PATH}")
    print(f"To   (droplet): {target_url.split('@')[-1]}\n")  # never echo the password
    lines, missing, src_meta, dst_meta = summarize(src_engine, dst_engine, content, customer)
    print("\n".join(lines))
    if missing:
        print(f"\nThe droplet database is missing table(s): {', '.join(missing)}.")
        print("Deploy the code first (deploy_all.sh step 2 creates them), then re-run.")
        sys.exit(1)

    answer = input(
        "\nThis ERASES the droplet's images/categories/sample sets and replaces them with the laptop's.\n"
        "Orders and shared designs are not touched. Type 'yes' to continue: "
    )
    if answer.strip().lower() != "yes":
        print("Skipped -- nothing on the droplet was changed.")
        return

    print()
    copy_content(src_engine, dst_engine, content, src_meta, dst_meta)
    print("\nDone. Content is live immediately (no restart needed).")


if __name__ == "__main__":
    main()
