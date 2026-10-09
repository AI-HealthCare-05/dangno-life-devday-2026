#!/usr/bin/env bash
set -euo pipefail
# Ubuntu 24.04 login user. Fetch a fresh, immutable release from main.
[[ $(id -u) != 0 ]] || { echo 'Run as Ubuntu login user.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Ubuntu 24.04 required.' >&2; exit 1; }
BASE="$HOME/dangno-life"
SHARED="$BASE/shared"
mkdir -p "$BASE/releases" "$SHARED/storage" "$SHARED/artifacts"
chmod 700 "$SHARED" "$SHARED/storage"
exec 9>"$BASE/deploy.lock"
flock -n 9 || { echo 'Deployment already running.' >&2; exit 1; }
sudo apt-get update
sudo apt-get install -y git python3-venv python3-dev build-essential libgomp1 nginx
STAGE=$(mktemp -d "$BASE/releases/staging.XXXXXX")
git clone --depth 1 --branch main https://github.com/AI-HealthCare-05/dangno-life-devday-2026.git "$STAGE"
SHA=$(git -C "$STAGE" rev-parse HEAD)
RELEASE="$BASE/releases/$SHA"
if [[ -e "$RELEASE" ]]; then echo 'Release already exists; review before redeploying.' >&2; exit 1; fi
mv "$STAGE" "$RELEASE"
cd "$RELEASE"
python3 restore_workspace.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-demo.lock.txt
# Model binaries, user data, and secrets remain outside the release checkout.
[[ ! -e storage ]] || { echo 'Unexpected storage in release.' >&2; exit 1; }
ln -s "$SHARED/storage" storage
[[ ! -e models/artifacts ]] || { echo 'Unexpected bundled model artifacts.' >&2; exit 1; }
ln -s "$SHARED/artifacts" models/artifacts
.venv/bin/python scripts/provision-models-google-drive.py
if [[ ! -f "$SHARED/.env" ]]; then
  umask 077
  .venv/bin/python - "$SHARED/.env" <<'PY'
from pathlib import Path
import secrets
import sys
Path(sys.argv[1]).write_text('\n'.join([
    'ENV=dev', 'SECRET_KEY=' + secrets.token_urlsafe(48),
    'DEMO_MODE=true', 'DEMO_ARTIFACT_INFERENCE_ENABLED=true',
    'PREDICTION_PROVIDER=artifact', 'COOKIE_DOMAIN=',
    'FRONTEND_BASE_URL=https://www.dang-no.life', 'OPENAI_API_KEY=',
]) + '\n')
PY
fi
chmod 600 "$SHARED/.env"
ln -s "$SHARED/.env" .env
USER_NAME=$(id -un)
SERVICE="$BASE/dangno-life.service"
cat >"$SERVICE" <<UNIT
[Unit]
Description=DangNO Life main release
After=network-online.target
Wants=network-online.target
[Service]
User=$USER_NAME
WorkingDirectory=$BASE/current
EnvironmentFile=$SHARED/.env
ExecStart=$BASE/current/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
UNIT
if sudo test -e /etc/systemd/system/dangno-life.service; then
  sudo cmp -s "$SERVICE" /etc/systemd/system/dangno-life.service || { echo 'Existing service differs; review it before replacement.' >&2; exit 1; }
fi
PREVIOUS=$(readlink "$BASE/current" || true)
ln -s "$RELEASE" "$BASE/current.next"
mv -Tf "$BASE/current.next" "$BASE/current"
sudo install -m 644 "$SERVICE" /etc/systemd/system/dangno-life.service
sudo systemctl daemon-reload
sudo systemctl enable dangno-life
sudo systemctl restart dangno-life
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8000/api/health; then
    echo; echo "Deployed main commit: $SHA"
    echo 'Configure DNS, Nginx and HTTPS; external deployment is not verified yet.'
    exit 0
  fi
  sleep 2
done
if [[ -n "$PREVIOUS" ]]; then
  ln -s "$PREVIOUS" "$BASE/current.rollback"
  mv -Tf "$BASE/current.rollback" "$BASE/current"
  sudo systemctl restart dangno-life
fi
echo 'Health check failed. Previous code restored when available; shared database is unchanged.' >&2
exit 1
