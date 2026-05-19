#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
PIPELINE_MODE="${1:-full}"
PIPELINE_LOG_DIR="${PIPELINE_LOG_DIR:-${REPO_ROOT}/logs}"
PIPELINE_TRAIN_MODEL="${PIPELINE_TRAIN_MODEL:-0}"
RUN_TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
RUN_LOG_PATH="${PIPELINE_LOG_DIR}/pipeline-${PIPELINE_MODE}-${RUN_TIMESTAMP}.log"
LATEST_LOG_PATH="${PIPELINE_LOG_DIR}/pipeline-latest.log"
LATEST_STATUS_PATH="${PIPELINE_LOG_DIR}/pipeline-latest.status"

mkdir -p "${PIPELINE_LOG_DIR}"
cd "${REPO_ROOT}"

exec > >(tee -a "${RUN_LOG_PATH}") 2>&1

log() {
    printf '[%s] %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$*"
}

write_status() {
    local status="$1"
    printf 'mode=%s\nstatus=%s\nlog=%s\nupdated_at=%s\n' \
        "${PIPELINE_MODE}" \
        "${status}" \
        "${RUN_LOG_PATH}" \
        "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "${LATEST_STATUS_PATH}"
    cp "${RUN_LOG_PATH}" "${LATEST_LOG_PATH}"
}

run_stage() {
    local stage_name="$1"
    shift

    log "START ${stage_name}: $*"
    if "$@"; then
        log "SUCCESS ${stage_name}"
        return 0
    else
        local exit_code=$?
        log "FAILED ${stage_name} (exit ${exit_code})"
        return "${exit_code}"
    fi
}

run_ingest_and_etl() {
    run_stage ingest "${PYTHON_BIN}" workers/ingest.py --incremental || return $?
    run_stage etl "${PYTHON_BIN}" workers/etl.py || return $?
}

run_prediction() {
    if [[ "${PIPELINE_TRAIN_MODEL}" == "1" ]]; then
        run_stage train "${PYTHON_BIN}" workers/train_model.py || return $?
    fi
    run_stage predict "${PYTHON_BIN}" workers/predict.py || return $?
}

main() {
    log "Pipeline mode: ${PIPELINE_MODE}"
    write_status running

    case "${PIPELINE_MODE}" in
        full)
            run_ingest_and_etl || return $?
            run_prediction || return $?
            ;;
        ingest-etl)
            run_ingest_and_etl || return $?
            ;;
        predict-only)
            run_prediction || return $?
            ;;
        train-predict)
            PIPELINE_TRAIN_MODEL=1 run_prediction || return $?
            ;;
        *)
            echo "Usage: ./scripts/run_pipeline.sh [full|ingest-etl|predict-only|train-predict]" >&2
            return 64
            ;;
    esac

    write_status succeeded
    log "Pipeline completed successfully."
}

main
exit_code=$?

if [[ "${exit_code}" -eq 0 ]]; then
    exit 0
fi

write_status failed
log "Pipeline failed."
exit "${exit_code}"
