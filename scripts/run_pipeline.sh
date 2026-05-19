#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "${REPO_ROOT}"

"${PYTHON_BIN}" workers/ingest.py --incremental
"${PYTHON_BIN}" workers/etl.py
"${PYTHON_BIN}" workers/predict.py
