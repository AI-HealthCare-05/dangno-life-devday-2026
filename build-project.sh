#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -f app/models/users.py ]; then python3 restore_workspace.py; fi
sh scripts/build-demo.sh
