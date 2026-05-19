# Backup and Maintenance

PostgreSQL runs in Docker Compose with persistent data in the `postgres_data` volume. The backup procedure uses `pg_dump` in custom format so the file can be restored with `pg_restore`.

## Daily Backup

Run:

```bash
./scripts/backup_db.sh backup
```

Defaults:
- output directory: `backups/postgres`
- file format: `air_quality_YYYYMMDDTHHMMSSZ.dump`
- retention: delete dump files older than 7 days

Configuration:

```bash
BACKUP_DIR=/var/backups/air-quality RETENTION_DAYS=7 ./scripts/backup_db.sh backup
```

To verify immediately after backup:

```bash
VERIFY_BACKUP=1 ./scripts/backup_db.sh backup
```

## Restore Verification

Run:

```bash
./scripts/backup_db.sh verify
```

The script restores the latest backup into a temporary database named `air_quality_restore_check`, runs smoke-count queries against `oltp.location` and `oltp.measurement_raw`, and then drops the temporary database.

## Restore Procedure

To restore manually into a new database:

```bash
docker compose cp backups/postgres/air_quality_YYYYMMDDTHHMMSSZ.dump db:/tmp/air_quality.dump
docker compose exec -T db createdb -U air_quality air_quality_restored
docker compose exec -T db pg_restore -U air_quality -d air_quality_restored --no-owner --no-acl /tmp/air_quality.dump
```

For production recovery, stop application writers first, restore into a temporary database, validate counts and key queries, then swap connection settings or replace the original database during a maintenance window.

## Maintenance

Run:

```bash
./scripts/backup_db.sh maintenance
```

This executes:
- `vacuumdb --analyze --verbose` to reclaim space where possible and refresh planner statistics.
- `REINDEX DATABASE air_quality` to rebuild database indexes after heavy churn or before demos.

Recommended schedule:
- daily backup at 02:15 UTC
- weekly maintenance at 02:45 UTC on Sunday

Install the example cron:

```bash
crontab scripts/air_quality_backup.crontab
```
