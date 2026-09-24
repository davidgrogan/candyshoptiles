# Deploying Candy Shop Tiles to the droplet

This app goes on the **same droplet as Paradise City Music**, set up the same way but kept completely separate:

| | Paradise City Music (don't touch) | Candy Shop Tiles |
|---|---|---|
| Folder | `/var/www/localarts` | `/var/www/candyshoptiles` |
| systemd unit | `local-music.service` | `candyshoptiles.service` |
| gunicorn port | 8000 | **8010** |
| Postgres db / user | `localarts` | `candyshoptiles` / `candyshoptiles` |
| URL | `waveyvibe.dev/localarts` | `waveyvibe.dev/candyshoptiles` |
| Laptop tunnel port | 5433 | 5434 |

Everything below is one-time setup, done as root over SSH. After this, every deploy is just `./deploy_all.sh` from your laptop, and you never edit code on the droplet.

## 0. Before you start: check what's already running

```bash
ssh root@YOUR_DROPLET_IP
ss -tlnp | grep -E ':80(00|10)\b'   # 8000 should be localarts; 8010 must be free
cat /etc/caddy/Caddyfile            # find the waveyvibe.dev { ... } block
```

If 8010 is taken, pick another free port. Use it in `deploy/candyshoptiles.service`, `deploy/Caddyfile.snippet.example` and `DROPLET_APP_PORT` in your laptop's `deploy/push_to_droplet.env`.

## 1. Push the code to GitHub

This is already done: the repo is `github.com/davidgrogan/candyshoptiles` and is public. Real secrets only ever live in the gitignored env files.

## 2. Create this app's own Postgres database and user

Postgres is already installed from the localarts setup. This only adds a new user and database. It doesn't touch `localarts`.

```bash
sudo -u postgres psql -c "CREATE USER candyshoptiles WITH PASSWORD 'CHOOSE_A_REAL_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE candyshoptiles OWNER candyshoptiles;"
```

Save that password. It goes in two places: `DATABASE_URL` on the droplet (step 4), and `DROPLET_PG_PASSWORD` on your laptop (step 8). Postgres only listens on localhost, so there's nothing to open in the firewall.

## 3. Clone the repo and create the virtualenv

```bash
cd /var/www
git clone https://github.com/davidgrogan/candyshoptiles.git candyshoptiles
cd candyshoptiles
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

(If `venv` complains about `ensurepip`, run `apt install python3.12-venv` and try again. This is the same fix as localarts.)

## 4. Configure the droplet's env file

```bash
cp deploy/candyshoptiles.env.example deploy/candyshoptiles.env
nano deploy/candyshoptiles.env
```

- **`DATABASE_URL`**: `postgresql://candyshoptiles:THE_PASSWORD@127.0.0.1:5432/candyshoptiles`
- **`SECRET_KEY`**: generate one with `python3 -c "import secrets; print(secrets.token_hex(32))"`
- **`ADMIN_PASSWORD_HASH`**: required, because there's no admin/admin fallback on Postgres. Generate it with:
  `.venv/bin/python -c "from werkzeug.security import generate_password_hash as g; print(g('your-real-password'))"`
- **`SESSION_COOKIE_NAME` / `SESSION_COOKIE_PATH`**: already set to `candyshoptiles_session` / `/candyshoptiles`, so this app's login cookie can't collide with localarts. If this app ever gets its own domain as well, unset `SESSION_COOKIE_PATH`. This is the same caveat as localarts' custom-domain note.
- **`RESEND_API_KEY` / `ORDER_NOTIFY_EMAIL`**: optional, for order emails. You can reuse the Resend key from localarts. Without them, orders still save and show up in Admin → Orders.

This file is gitignored. Never commit it.

## 5. Create the tables

```bash
set -a; source deploy/candyshoptiles.env; set +a
.venv/bin/python sync_schema.py    # creates all tables, then reports "Schema is up to date"
```

Don't run `seed.py` here. Content comes from your laptop in step 9. Also note that a fresh shell doesn't have `DATABASE_URL` set until you re-run that `set -a; source ...` line. Without it, ad-hoc scripts silently fall back to an empty SQLite file instead of Postgres. This is the same gotcha as localarts.

## 6. Install the systemd service

```bash
cp /var/www/candyshoptiles/deploy/candyshoptiles.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now candyshoptiles.service

systemctl status candyshoptiles.service --no-pager
curl -s http://127.0.0.1:8010/healthz     # -> ok
```

If it fails to start, run `journalctl -u candyshoptiles -n 50`.

## 7. Add it to Caddy

```bash
cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak.$(date +%F)
nano /etc/caddy/Caddyfile
```

Inside the existing `waveyvibe.dev { ... }` block, paste the snippet from `deploy/Caddyfile.snippet.example`:

- put it after the `handle_path /localarts/*` block
- put it before `root * /var/www/waveyvibe` and `file_server`
- leave the localarts block exactly as it is

```caddy
redir /candyshoptiles /candyshoptiles/ 308
handle_path /candyshoptiles/* {
    request_body {
        max_size 60MB
    }
    reverse_proxy localhost:8010 {
        header_up X-Forwarded-Prefix "/candyshoptiles"
    }
}
```

Then run:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
curl -sI https://waveyvibe.dev/candyshoptiles/ | head -1     # 200
curl -sI https://waveyvibe.dev/localarts/ | head -1          # still 200 -- localarts unaffected
```

`handle_path` strips `/candyshoptiles` before proxying. `wsgi.py`'s `ProxyFix(x_prefix=1)` reads `X-Forwarded-Prefix` so that every generated link, static file and share URL comes out as `/candyshoptiles/...`. This is the same mechanism localarts uses.

If waveyvibe.dev's homepage lists its apps, add a card for `/candyshoptiles` there too.

## 8. Set up deploys from your laptop

```bash
cd ~/code/candyshoptiles
cp deploy/push_to_droplet.env.example deploy/push_to_droplet.env
nano deploy/push_to_droplet.env     # droplet IP, SSH user (root), the candyshoptiles Postgres password
```

This file is gitignored. The script uses the same password-based SSH you already use by hand, and asks for the password once per run.

## 9. First deploy

```bash
./deploy_all.sh
```

This time the code step is a no-op (the droplet already has it). Then:

1. The images rsync over.
2. The content sync shows your laptop's counts (16 placeholder images, 4 categories, 4 sets) against the droplet's (all 0).
3. Type **yes** to copy them up.
4. Visit https://waveyvibe.dev/candyshoptiles.

---

## Every deploy after that

1. Make your changes locally: code, and/or images and sets through the local admin at `http://127.0.0.1:5051/admin`.
2. Run `./deploy_all.sh`, or double-click **Deploy Everything.command**.

### What deploy_all.sh does, and why it's safe

It opens **one** SSH connection (a ControlMaster socket) that carries every remote command, the rsync, and the Postgres tunnel on local port 5434. It then:

1. **Commits and pushes.** It asks for a commit message and aborts if you leave it blank.
2. **On the droplet:**
   - `git pull --ff-only`, which refuses rather than merges if the droplet's checkout ever diverged
   - `pip install -r requirements.txt`
   - `sync_schema.py --apply`: it only runs `ADD COLUMN` and widening `ALTER COLUMN ... TYPE`, and never drops, renames or narrows anything
   - `systemctl restart`, then polls `/healthz` for up to 15 seconds
3. **Content:**
   - rsyncs `app/static/uploads/`. There's no `--delete`, so nothing on the droplet is ever removed.
   - runs `sync_content.py`, which prints laptop-vs-droplet row counts and waits for you to type `yes`. Anything else skips it, and nothing changes.

### What the content sync replaces and what it never touches

Each table in `app/models.py` is marked **content** or **customer**:

- **Replaced from your laptop:** `art_image`, `category`, `image_categories`, `sample_set`.
- **Never touched:** `order_request`, `saved_design`. Real customers create these on the live site. Your laptop's copies are just test data.

So manage images and sets **locally**. Anything you change in the *live* admin's Images, Categories or Sets pages is overwritten by the next sync, and those pages show a banner saying so. Handling orders in the live admin (status and notes) is fine, because the sync never touches orders.

If you ever add a table, give it `info=CONTENT` or `info=CUSTOMER` in `models.py`. `sync_content.py` refuses to run while any table is unmarked, so a new table can't silently land in the wrong bucket. This is the bug that bit localarts' hand-maintained table list three times.

### Adding a column

Add it to the model. On your laptop it appears the next time the app starts. On the droplet, `deploy_all.sh` adds it. If it's `nullable=False`, also give it a `server_default=`, or Postgres can't backfill existing rows.

To preview pending schema changes on the droplet without applying them:

```bash
cd /var/www/candyshoptiles && set -a && source deploy/candyshoptiles.env && set +a && .venv/bin/python sync_schema.py
```

### Backing up orders

Orders exist only on the droplet, so back them up now and then:

```bash
sudo -u postgres pg_dump candyshoptiles > ~/candyshoptiles-$(date +%F).sql
```
