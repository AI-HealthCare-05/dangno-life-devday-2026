#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <app-version> <ai-worker-version>" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_VERSION="$1"
AI_WORKER_VERSION="$2"
: "${DOCKER_USER:?Set DOCKER_USER after completing docker login.}"
: "${DOCKER_REPOSITORY:?Set DOCKER_REPOSITORY after completing docker login.}"

cd "$ROOT_DIR"
docker build --platform linux/amd64 -f app/Dockerfile -t "$DOCKER_USER/$DOCKER_REPOSITORY:app-$APP_VERSION" .
docker build --platform linux/amd64 -f ai_worker/Dockerfile -t "$DOCKER_USER/$DOCKER_REPOSITORY:ai-$AI_WORKER_VERSION" .
docker build --platform linux/amd64 -f infra/nginx/Dockerfile -t "$DOCKER_USER/$DOCKER_REPOSITORY:web-$APP_VERSION" .
docker push "$DOCKER_USER/$DOCKER_REPOSITORY:app-$APP_VERSION"
docker push "$DOCKER_USER/$DOCKER_REPOSITORY:ai-$AI_WORKER_VERSION"
docker push "$DOCKER_USER/$DOCKER_REPOSITORY:web-$APP_VERSION"

echo "Images pushed. Set APP_VERSION=$APP_VERSION and AI_WORKER_VERSION=$AI_WORKER_VERSION in the EC2 .env."
