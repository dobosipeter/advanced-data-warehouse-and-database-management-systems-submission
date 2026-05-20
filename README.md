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

The repository now includes the local stack, schema initialization, ingestion worker, FastAPI backend, PM2.5 training/prediction pipeline, and both operational and analytical Streamlit pages.

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

The pipeline script supports the following modes:

- `./scripts/run_pipeline.sh full` — incremental ingest → ETL → train if the model artifact is missing → predict
- `./scripts/run_pipeline.sh ingest-etl` — incremental ingest → ETL
- `./scripts/run_pipeline.sh predict-only` — generate predictions from the latest trained model, training first if the artifact is missing
- `./scripts/run_pipeline.sh train-predict` — retrain the PM2.5 model, then predict

Each run writes a timestamped log under `logs/` plus `logs/pipeline-latest.log` and `logs/pipeline-latest.status` so scheduled executions leave an audit trail.

The API now exposes the operational and analytical endpoints from PostgreSQL:

- `GET /health`
- `GET /locations`
- `GET /measurements`
- `GET /alerts`
- `PATCH /alerts/{pollution_alert_id}`
- `GET /thresholds`
- `POST /thresholds`
- `PATCH /thresholds/{threshold_rule_id}`
- `GET /ingestion-runs`
- `GET /predictions` (supports city/location/parameter/date filters and returns predicted risk plus matched actual/error when available)
- `POST /demo/refresh` (token-protected, optional command wiring)

The Streamlit frontend consumes the API through `API_BASE_URL` and includes:

- operational pages for overview, station exploration, threshold management, alert review, and system status
- analytical pages for air quality overview, high-risk periods, prediction insights, and data operations

`oltp.measurement_raw` is monthly range-partitioned on `measured_at` and indexed for time-series access. The indexing rationale and verification query are documented in `docs/03-indexing-and-partitioning.md`.

Database backup and maintenance operations are handled by `scripts/backup_db.sh`. The script creates compressed PostgreSQL custom-format dumps, prunes old backups, can restore-check the latest dump, and runs maintenance commands. Details are documented in `docs/04-backup-and-maintenance.md`.

The data warehouse star schema is defined in `database/init/003_create_dw_tables.sql`; its ER diagram is available as Mermaid source in `diagrams/dw_star_schema.mmd`.

Additional Mermaid sources for the system architecture, deployment architecture, and end-to-end data flow are tracked under `diagrams/` for report and presentation reuse.

Run the OLTP-to-DW ETL manually with:

```bash
docker compose run --rm worker python etl.py
```

The ETL applies SCD2 versioning to location and sensor dimensions: changed source metadata expires the previous current row and inserts a new current surrogate-key version.

Train the PM2.5 model manually with:

```bash
docker compose run --rm worker python train_model.py
```

Generate the latest PM2.5 predictions manually with:

```bash
docker compose run --rm worker python predict.py
```

The incremental ingestion uses the latest successful `oltp.ingestion_run_log.finished_at` value as its lower bound, falling back to `started_at` for legacy/incomplete log rows, and relies on the unique `(sensor_id, measured_at)` constraint to skip already loaded measurements.

New PM2.5 measurements now also drive the operational alert workflow: the ingestion worker ensures default city threshold rules exist for PM2.5, a PostgreSQL trigger creates `oltp.pollution_alert` rows with status `open` for moderate/high/critical readings, and an `audit.pollution_alert_outbox` table records alert events for downstream jobs.

The ingestion worker now runs with explicit transaction boundaries: each location is processed as a batch transaction, each sensor runs inside a savepoint, failed sensor batches are rolled back without corrupting successful batches, and `oltp.ingestion_run_log` ends as `succeeded`, `partial`, or `failed` with summarized error details.

An example cron configuration is provided in `scripts/air_quality_pipeline.crontab`. It refreshes ingest+ETL every 3 hours and runs prediction daily:

```bash
crontab scripts/air_quality_pipeline.crontab
```

Deployment and server-access notes for the current Hetzner VM flow are tracked in `docs/05-hetzner-access-and-deployment.md`.

For public deployment behind Caddy, set the reverse proxy ports in `.env` to:

```bash
PROXY_PORT=80
PROXY_TLS_PORT=443
```

The database, API, and frontend ports are bound to `127.0.0.1` by default so they stay host-local while Caddy is the only public entrypoint.

GitHub Actions deployment is defined in `.github/workflows/deploy.yml`. It syncs the repository to the Hetzner VM over SSH, runs `scripts/deploy_stack.sh`, and verifies the public dashboard and API URLs after each deployment.
