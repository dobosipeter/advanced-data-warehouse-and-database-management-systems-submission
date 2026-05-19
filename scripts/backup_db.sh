#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

POSTGRES_DB="${POSTGRES_DB:-air_quality}"
POSTGRES_USER="${POSTGRES_USER:-air_quality}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-db}"
VERIFY_BACKUP="${VERIFY_BACKUP:-0}"

usage() {
    cat <<USAGE
Usage: $0 [backup|verify|maintenance]

Commands:
  backup       Create a compressed pg_dump custom-format backup and prune old files.
  verify       Restore the latest backup into a temporary database and run smoke checks.
  maintenance  Run VACUUM ANALYZE and REINDEX DATABASE.

Environment:
  POSTGRES_DB       Database name. Default: air_quality
  POSTGRES_USER     Database user. Default: air_quality
  BACKUP_DIR        Backup output directory. Default: ./backups/postgres
  RETENTION_DAYS    Delete backup files older than this many days. Default: 7
  COMPOSE_SERVICE   PostgreSQL compose service. Default: db
  VERIFY_BACKUP     Set to 1 to verify immediately after backup.
USAGE
}

compose_exec() {
    docker compose -f "${REPO_ROOT}/docker-compose.yml" exec -T "${COMPOSE_SERVICE}" "$@"
}

latest_backup() {
    find "${BACKUP_DIR}" -maxdepth 1 -type f -name "${POSTGRES_DB}_*.dump" -printf '%T@ %p\n' \
        | sort -nr \
        | awk 'NR == 1 {print $2}'
}

backup_database() {
    mkdir -p "${BACKUP_DIR}"

    local timestamp
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    local backup_path="${BACKUP_DIR}/${POSTGRES_DB}_${timestamp}.dump"

    compose_exec pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc --no-owner --no-acl > "${backup_path}"
    find "${BACKUP_DIR}" -maxdepth 1 -type f -name "${POSTGRES_DB}_*.dump" -mtime "+${RETENTION_DAYS}" -delete

    printf 'Created backup: %s\n' "${backup_path}"

    if [[ "${VERIFY_BACKUP}" == "1" ]]; then
        verify_backup "${backup_path}"
    fi
}

verify_backup() {
    local backup_path="${1:-}"
    if [[ -z "${backup_path}" ]]; then
        backup_path="$(latest_backup)"
    fi
    if [[ -z "${backup_path}" || ! -f "${backup_path}" ]]; then
        printf 'No backup file found to verify.\n' >&2
        return 1
    fi

    local temp_db="${POSTGRES_DB}_restore_check"
    local container_backup="/tmp/$(basename "${backup_path}")"

    docker compose -f "${REPO_ROOT}/docker-compose.yml" cp "${backup_path}" "${COMPOSE_SERVICE}:${container_backup}"
    compose_exec dropdb -U "${POSTGRES_USER}" --if-exists "${temp_db}"
    compose_exec createdb -U "${POSTGRES_USER}" "${temp_db}"
    compose_exec pg_restore -U "${POSTGRES_USER}" -d "${temp_db}" --no-owner --no-acl "${container_backup}"
    compose_exec psql -U "${POSTGRES_USER}" -d "${temp_db}" -v ON_ERROR_STOP=1 -tAc \
        "SELECT 'locations=' || count(*) FROM oltp.location UNION ALL SELECT 'measurements=' || count(*) FROM oltp.measurement_raw"
    compose_exec dropdb -U "${POSTGRES_USER}" --if-exists "${temp_db}"
    compose_exec rm -f "${container_backup}"

    printf 'Verified backup: %s\n' "${backup_path}"
}

run_maintenance() {
    compose_exec vacuumdb -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --analyze --verbose
    compose_exec psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c \
        "REINDEX DATABASE ${POSTGRES_DB};"
}

command="${1:-backup}"
case "${command}" in
    backup)
        backup_database
        ;;
    verify)
        verify_backup "${2:-}"
        ;;
    maintenance)
        run_maintenance
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
