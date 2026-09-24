# Candy Shop Tiles

Customers pick 8″ × 10″ art tiles from a palette, drag them (or tap them) onto a wall that grows in any direction, and watch the price update as they go. They can preview the wall on a built-in room photo or on a photo of their own wall, send someone a share link, and submit an order request.

Pricing, set in `app/pricing.py`:

- one tile: $49
- two or more tiles: $39 each
- an optional sample tile: $29, limited to one per order

Live at **https://waveyvibe.dev/candyshoptiles**, on the same droplet as Paradise City Music but in its own folder, service and database.

## Local development

```bash
cd ~/code/candyshoptiles
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python seed.py      # placeholder art, categories, sample sets (only when the library is empty)
.venv/bin/python run.py       # http://127.0.0.1:5051
```

- **Database:** SQLite at `instance/candyshoptiles.sqlite3` is used automatically when `DATABASE_URL` isn't set. New model columns are added to it automatically every time the app starts.
- **Admin:** `/admin`, with login `admin` / `admin` locally. This fallback only works on SQLite; production needs `ADMIN_PASSWORD_HASH`.
- **Tests:** `.venv/bin/python -m pytest`
- **Config:** copy `.env.example` to `.env` if you want to set anything locally. Nothing is required.

## Deploying

All code and content changes happen on your laptop. Run:

```bash
./deploy_all.sh          # or double-click "Deploy Everything.command"
```

It does the following, in order:

1. Commits your changes (asks for a message) and pushes.
2. Over one SSH connection, on the droplet:
   - `git pull`
   - `pip install`
   - `sync_schema.py --apply`, which adds or widens columns and never drops anything
   - restarts the service and runs a health check
3. Rsyncs the uploaded images, then shows laptop-vs-droplet counts. If you type **yes**, it replaces the droplet's images, categories and sample sets with your local copy. **Orders and shared designs on the droplet are never touched.**

One-time droplet setup is in [DEPLOY.md](DEPLOY.md).

## How it's put together

| Path | What it is |
|---|---|
| `app/__init__.py` | `create_app()`: config from environment variables, blueprints, local SQLite auto-schema-sync |
| `app/models.py` | Models. Every table is marked **content** (managed locally, synced up) or **customer** (live-only, never synced) |
| `app/layout.py` | Grid layouts: a sparse list of `{r, c, image_id}`, validated and normalized on the server |
| `app/pricing.py` | Prices and tile size, the only place they're defined |
| `app/routes/main.py` | Designer (`/`), share links (`/d/<slug>`, `POST /api/designs`), sample sets (`/sets`), `/healthz` |
| `app/routes/orders.py` | Order-request form and submit. The total is recomputed on the server |
| `app/routes/admin.py` | Images (bulk upload, edit, replace, hide, delete), categories, sample sets, orders |
| `app/static/designer.js` | Drag-and-drop board, using pointer events so it works with a mouse or touch |
| `app/static/wall.js` | View-on-wall. The customer's photo stays in their browser |
| `app/schema_sync.py`, `sync_schema.py` | Non-destructive schema sync |
| `sync_content.py` | Laptop to droplet content copy (content tables only) |
| `app/placeholders.py`, `tools/make_walls.py` | Generated placeholder art and wall backgrounds |

**Uploaded images** go in `app/static/uploads/art/`, which is gitignored and synced by `deploy_all.sh`. Every upload is re-encoded by Pillow into a full-size image (max 2000px) and a thumbnail (max 480px). This strips metadata and GPS data.

**Replacing the placeholder walls:** overwrite `app/static/walls/{painted,sofa,entry}.jpg` with real photos. Then set each wall's `inches` in `app/templates/_wall.html` to how many inches of wall the photo spans, so the tiles stay true to scale.
