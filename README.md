# Air Quality Intelligence System

Combined submission for Advanced Data Warehouse Technologies and Advanced Database Management Systems.

The project ingests air quality measurements from the OpenAQ API, stores operational monitoring data in PostgreSQL, transforms measurements into a data warehouse, and exposes the results through a FastAPI backend and Streamlit dashboard.

## Planned Stack

- PostgreSQL 16 for staging, OLTP, DW, ML, and audit schemas
- FastAPI for REST endpoints and Swagger documentation
- Streamlit for the operational GUI and analytical dashboard
- Python workers for OpenAQ ingestion, ETL, model training, and prediction
- Docker Compose for local development
- Caddy for production reverse proxying

## Quick Start

1. Copy `.env.example` to `.env` and fill in secrets as needed.
2. Start the local stack:

   ```bash
   docker compose up
   ```

3. Open the services:

   - Frontend: http://localhost:8501
   - API docs: http://localhost:8001/docs
   - Reverse proxy: http://localhost:8080

The repository already includes the local stack, schema initialization, and OpenAQ ingestion worker. The API, ETL, prediction, and dashboard layers are still being expanded.

## Pipeline Operations

Run the initial historical ingestion manually:

```bash
python workers/ingest.py --initial
```

Run the incremental ingestion manually:

```bash
python workers/ingest.py --incremental
```

Run the end-to-end scheduled pipeline entrypoint:

```bash
./scripts/run_pipeline.sh
```

The API now exposes the first operational endpoints from PostgreSQL:

- `GET /health`
- `GET /locations`
- `GET /measurements`
- `GET /alerts`
- `PATCH /alerts/{pollution_alert_id}`
- `GET /thresholds`
- `POST /thresholds`
- `PATCH /thresholds/{threshold_rule_id}`
- `GET /ingestion-runs`
- `GET /predictions`
- `POST /demo/refresh` (token-protected, optional command wiring)

The Streamlit frontend consumes the API through `API_BASE_URL` and includes pages for operational overview, station exploration, threshold management, alert review, and system status.

`oltp.measurement_raw` is monthly range-partitioned on `measured_at` and indexed for time-series access. The indexing rationale and verification query are documented in `docs/03-indexing-and-partitioning.md`.

Database backup and maintenance operations are handled by `scripts/backup_db.sh`. The script creates compressed PostgreSQL custom-format dumps, prunes old backups, can restore-check the latest dump, and runs maintenance commands. Details are documented in `docs/04-backup-and-maintenance.md`.

The incremental ingestion uses the latest successful `oltp.ingestion_run_log.finished_at` value as its lower bound, falling back to `started_at` for legacy/incomplete log rows, and relies on the unique `(sensor_id, measured_at)` constraint to skip already loaded measurements.

New PM2.5 measurements now also drive the operational alert workflow: the ingestion worker ensures default city threshold rules exist for PM2.5, a PostgreSQL trigger creates `oltp.pollution_alert` rows with status `open` for moderate/high/critical readings, and an `audit.pollution_alert_outbox` table records alert events for downstream jobs.

The ingestion worker now runs with explicit transaction boundaries: each location is processed as a batch transaction, each sensor runs inside a savepoint, failed sensor batches are rolled back without corrupting successful batches, and `oltp.ingestion_run_log` ends as `succeeded`, `partial`, or `failed` with summarized error details.

An example cron configuration is provided in `scripts/air_quality_pipeline.crontab`. It runs the pipeline every 3 hours:

```bash
crontab scripts/air_quality_pipeline.crontab
```
