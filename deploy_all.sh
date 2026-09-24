#!/bin/bash
# Ship everything: commit + push local code, pull it onto the droplet,
# sync the droplet's Postgres schema, restart the service, then sync
# uploaded images and (if you type "yes") your local content.
#
# Same routine as Paradise City Music's deploy_all.sh, for this app's own
# folder/service/database on the same droplet. Order matters:
#   code first   -- sync_schema.py compares the database against whatever
#                   app/models.py says *on the droplet*, so the droplet
#                   needs today's code before it can see today's columns;
#   schema second, then restart;
#   images before data -- so an image row never goes live before its file.
#
# Steps:
#   1. Commit any uncommitted changes (prompts for a message) and push.
#   2. Over ONE SSH connection (ControlMaster), on the droplet:
#        git pull --ff-only, pip install -r requirements.txt,
#        sync_schema.py --apply   (adds missing columns / widens narrow
#                                  ones; never drops or narrows anything),
#        systemctl restart, then a health check.
#   3. rsync app/static/uploads/ (gitignored, so git pull never brings it),
#      then sync_content.py through the same connection's tunnel: shows
#      laptop-vs-droplet row counts and asks you to type "yes" before
#      replacing the droplet's images/categories/sample sets. Orders and
#      shared designs on the droplet are never touched.
#
# One-time setup: cp deploy/push_to_droplet.env.example deploy/push_to_droplet.env
# and fill it in (see DEPLOY.md). Uses the same password-based SSH you use
# by hand -- you're asked for the password once, when the connection opens.
set -euo pipefail

cd "$(dirname "$0")"

ENV_FILE="deploy/push_to_droplet.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE."
  echo "Copy deploy/push_to_droplet.env.example to $ENV_FILE and fill in your"
  echo "droplet's IP, SSH user, and the candyshoptiles Postgres password, then run this again."
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${DROPLET_SSH_USER:?Set DROPLET_SSH_USER in $ENV_FILE}"
: "${DROPLET_IP:?Set DROPLET_IP in $ENV_FILE}"
: "${DROPLET_PG_PASSWORD:?Set DROPLET_PG_PASSWORD in $ENV_FILE}"
# 5434, not 5433 -- so this can run while Paradise City Music's tunnel is up.
LOCAL_TUNNEL_PORT="${LOCAL_TUNNEL_PORT:-5434}"
DROPLET_APP_DIR="${DROPLET_APP_DIR:-/var/www/candyshoptiles}"
DROPLET_SERVICE_NAME="${DROPLET_SERVICE_NAME:-candyshoptiles.service}"
DROPLET_APP_PORT="${DROPLET_APP_PORT:-8010}"
PG_DB="${DROPLET_PG_DB:-candyshoptiles}"
PG_USER="${DROPLET_PG_USER:-candyshoptiles}"
UPLOADS_DIR="app/static/uploads"
REMOTE="${DROPLET_SSH_USER}@${DROPLET_IP}"

PYTHON=".venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

# --- Step 1: commit + push ---------------------------------------------------

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" != "main" ]; then
  echo "You're on branch '$BRANCH', not 'main' -- the droplet tracks main."
  read -r -p "Press Enter to continue anyway, or Ctrl-C to abort..."
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Uncommitted changes:"
  git status --short
  echo
  read -r -p "Commit message: " COMMIT_MSG
  if [ -z "$COMMIT_MSG" ]; then
    echo "No commit message entered -- aborting so nothing is committed with a blank message."
    exit 1
  fi
  git add -A
  git commit -m "$COMMIT_MSG"
else
  echo "No uncommitted changes -- skipping commit."
fi

echo "Pushing to origin..."
git push

# --- One SSH connection for everything below ---------------------------------

CONTROL_SOCKET="/tmp/candyshoptiles_deploy_$$"

cleanup() {
  if [ -S "$CONTROL_SOCKET" ]; then
    echo "Closing SSH connection..."
    ssh -S "$CONTROL_SOCKET" -O exit "$REMOTE" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "Opening SSH connection to ${DROPLET_IP} (you may be asked for your password)..."
if ! ssh -f -N -M -S "$CONTROL_SOCKET" \
    -o ExitOnForwardFailure=yes \
    -L "${LOCAL_TUNNEL_PORT}:localhost:5432" \
    "$REMOTE"; then
  echo "Could not open the SSH connection -- check DROPLET_IP/DROPLET_SSH_USER in $ENV_FILE,"
  echo "and that nothing else on your Mac is using port ${LOCAL_TUNNEL_PORT}."
  exit 1
fi

# --- Step 2: pull, install, schema sync, restart -----------------------------

echo
echo "--- Step 2: updating code + schema on the droplet ---"
ssh -S "$CONTROL_SOCKET" "$REMOTE" bash -s <<REMOTE_SCRIPT
set -euo pipefail
cd "${DROPLET_APP_DIR}"
git pull --ff-only
source .venv/bin/activate
pip install -q -r requirements.txt
set -a; source deploy/candyshoptiles.env; set +a
python3 sync_schema.py --apply
deactivate
systemctl restart "${DROPLET_SERVICE_NAME}"
for i in \$(seq 1 15); do
  if curl -fsS -o /dev/null "http://127.0.0.1:${DROPLET_APP_PORT}/healthz"; then
    echo "Service restarted and answering on port ${DROPLET_APP_PORT}."
    exit 0
  fi
  sleep 1
done
echo "WARNING: service didn't answer /healthz within 15s. Check: journalctl -u ${DROPLET_SERVICE_NAME} -n 50"
exit 1
REMOTE_SCRIPT

# --- Step 3: images, then content --------------------------------------------

echo
echo "--- Step 3: syncing uploaded images + content ---"

# A brand-new checkout may not have any uploads yet; rsync would error on a
# missing source directory instead of just copying nothing.
mkdir -p "$UPLOADS_DIR"
ssh -S "$CONTROL_SOCKET" "$REMOTE" "mkdir -p '${DROPLET_APP_DIR}/${UPLOADS_DIR}'"
# No --delete: an image deleted locally just lingers on the droplet as an
# unused file, rather than rsync ever removing anything there.
rsync -az -e "ssh -S $CONTROL_SOCKET" \
  "${UPLOADS_DIR}/" "${REMOTE}:${DROPLET_APP_DIR}/${UPLOADS_DIR}/"
echo "Images synced."

echo "Waiting for the database tunnel..."
for _ in $(seq 1 15); do
  nc -z localhost "$LOCAL_TUNNEL_PORT" 2>/dev/null && break
  sleep 1
done
if ! nc -z localhost "$LOCAL_TUNNEL_PORT" 2>/dev/null; then
  echo "Tunnel never came up on port $LOCAL_TUNNEL_PORT -- skipping the content sync."
  echo "(Code, schema and images above already went through.)"
  exit 1
fi

echo
"$PYTHON" sync_content.py \
  "postgresql://${PG_USER}:${DROPLET_PG_PASSWORD}@localhost:${LOCAL_TUNNEL_PORT}/${PG_DB}"

echo
echo "All done: code pushed + pulled, schema synced, service restarted, images synced."
