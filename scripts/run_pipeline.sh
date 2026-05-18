#!/usr/bin/env bash
set -euo pipefail

python workers/ingest.py --incremental
python workers/etl.py
python workers/predict.py
