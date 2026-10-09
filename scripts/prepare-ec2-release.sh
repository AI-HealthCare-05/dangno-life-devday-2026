#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-}"
ENV_FILE="${2:-$ROOT_DIR/.env}"
COMPOSE_FILE="$ROOT_DIR/infra/docker/docker-compose.prod.yml"

if [[ "$MODE" != "http" && "$MODE" != "https" ]]; then
  echo "Usage: $0 <http|https> [path-to-.env]" >&2
  exit 2
fi

server_name="$(awk -F= '$1 == "SERVER_NAME" {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE")"
if [[ ! "$server_name" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "ERROR: SERVER_NAME must be a domain name or EC2 public DNS name." >&2
  exit 1
fi

"$ROOT_DIR/scripts/preflight-production.sh" "$ENV_FILE"

template="$ROOT_DIR/infra/nginx/prod_${MODE}.conf.template"
runtime_dir="$ROOT_DIR/infra/nginx/runtime"
mkdir -p "$runtime_dir"
sed "s/__SERVER_NAME__/${server_name}/g" "$template" >"$runtime_dir/default.conf"

if [[ "$MODE" == "https" ]]; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh certbot \
    -c "test -f /etc/letsencrypt/live/${server_name}/fullchain.pem"
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo "Release services started in ${MODE} mode. Run the smoke tests in docs/EC2_PRODUCTION_DEPLOYMENT_CHECKLIST.md before announcing availability."
