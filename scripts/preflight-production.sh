#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"
COMPOSE_FILE="$ROOT_DIR/infra/docker/docker-compose.prod.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: production environment file not found: $ENV_FILE" >&2
  exit 1
fi

required=(
  COMPOSE_PROJECT_NAME DOCKER_USER DOCKER_REPOSITORY APP_VERSION AI_WORKER_VERSION
  SECRET_KEY COOKIE_DOMAIN DB_PORT DB_USER DB_PASSWORD DB_ROOT_PASSWORD DB_NAME
  REDIS_DB REDIS_STREAM REDIS_CONSUMER_GROUP REDIS_JOB_TTL_SECONDS
  MODEL_URI PREDICTION_MODEL_VERSION PREDICTION_FEATURE_SCHEMA_VERSION
  PREDICTION_THRESHOLD_VERSION SERVER_NAME CERTBOT_EMAIL
)

read_env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"
}

for key in "${required[@]}"; do
  value="$(read_env_value "$key")"
  if [[ -z "$value" ]]; then
    echo "ERROR: $key must be set in $ENV_FILE" >&2
    exit 1
  fi
  if [[ "$value" == *"replace-with"* || "$value" == "your-domain.example" || "$value" == "team@example.com" ]]; then
    echo "ERROR: $key still contains an example value" >&2
    exit 1
  fi
done

if [[ "$(read_env_value ENV)" != "prod" || "$(read_env_value DEMO_MODE)" != "false" ]]; then
  echo "ERROR: ENV=prod and DEMO_MODE=false are required for production." >&2
  exit 1
fi

if [[ "$(read_env_value DB_GENERATE_SCHEMAS)" != "false" ]]; then
  echo "ERROR: DB_GENERATE_SCHEMAS=false is required; use committed migrations." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Engine and Docker Compose v2 are required." >&2
  exit 1
fi

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet
echo "Production preflight passed: Compose syntax, required values, and production guardrails verified."
