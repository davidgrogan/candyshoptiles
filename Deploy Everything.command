#!/bin/bash
# Double-click in Finder to run deploy_all.sh in a fresh Terminal window.
# See deploy_all.sh for setup and what it does.
cd "$(dirname "$0")"
./deploy_all.sh
echo
read -r -p "Done -- press Enter to close this window..."
