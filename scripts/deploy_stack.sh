#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
APP_URL="${APP_URL:-https://mw79on-demo.online}"
API_URL="${API_URL:-https://api.mw79on-demo.online/docs}"

cd "${REPO_ROOT}"

docker compose up -d --build
docker compose ps

curl -fsSIL --retry 5 --retry-delay 5 --retry-connrefused "${APP_URL}" >/dev/null
curl -fsSIL --retry 5 --retry-delay 5 --retry-connrefused "${API_URL}" >/dev/null

printf 'Deployment completed successfully.\n'
