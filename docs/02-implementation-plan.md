# Implementation Plan

## Purpose

This document breaks the project into bite-sized, agent-executable work items. Each item is designed to fit within a single LLM context window session. Items include explicit inputs, outputs, dependencies, and acceptance criteria.

**Read `01-context-registry.md` first for all paths, schemas, and technology choices.**

---

## How to Use This Plan

1. Check the **Status** column or Azure DevOps board for current progress.
2. Pick the next `Ready` item (all dependencies met).
3. Read the item's description — it should be self-contained with the context registry.
4. Execute the work.
5. Mark as `Done` here and on the board.
6. Update `01-context-registry.md` if you discovered new information.

**Status values:** `Blocked` → `Ready` → `In Progress` → `Done`

---

## Phase 0: Foundation

### WI-01: Project Scaffolding & Repository Setup
| Field | Value |
|---|---|
| Azure DevOps | Issue #50 |
| Status | Done |
| Dependencies | None |
| Inputs | Target file structure from context registry §6 |
| Outputs | Complete directory structure, .gitignore, .env.example, README.md, pyproject.toml or requirements.txt stubs |
| Acceptance | `docker-compose.yml` exists (even if services are stubs), all directories created, repo is clean |

**Scope:**
- Create all directories: frontend/, api/, workers/, database/init/, reverse-proxy/, scripts/, reports/dbms/, reports/dw/, slides/dbms/, slides/dw/, diagrams/, tests/
- Create `.gitignore` (Python, Docker, .env, __pycache__, .venv, *.pdf in reports)
- Create `.env.example` with all required variables
- Create stub `docker-compose.yml` with service definitions (can use placeholder images initially)
- Create `README.md` with project title, description, quick-start instructions
- Create `requirements.txt` or `pyproject.toml` stubs for each Python service

---

### WI-02: PostgreSQL Database Setup & Schema Init
| Field | Value |
|---|---|
| Azure DevOps | Issue #51 |
| Status | Done |
| Dependencies | WI-01 |
| Inputs | Schema design from context registry §5 |
| Outputs | SQL init scripts in database/init/, working PostgreSQL container |
| Acceptance | `docker compose up db` starts PostgreSQL with all schemas created, can connect and list schemas |

**Scope:**
- `database/init/001_create_schemas.sql` — CREATE SCHEMA staging, oltp, dw, ml, audit
- `database/init/002_create_oltp_tables.sql` — All OLTP tables from context registry §5 (Location, Sensor, Parameter, MeasurementRaw, ThresholdRule, PollutionAlert, IngestionRunLog)
- `database/init/003_create_dw_tables.sql` — All DW tables (facts + dimensions with SCD2 fields)
- `database/init/004_create_indexes.sql` — Primary indexes, foreign keys
- `database/init/005_seed_parameters.sql` — Seed DimRiskClass and Parameter table with known pollutants
- Update `docker-compose.yml` db service to mount init scripts

---

### WI-03: Docker Compose & Local Dev Environment
| Field | Value |
|---|---|
| Azure DevOps | Issue #54 |
| Status | Done |
| Dependencies | WI-01 |
| Inputs | Service list from context registry §6, deployment docs |
| Outputs | Complete docker-compose.yml, all Dockerfiles |
| Acceptance | `docker compose up` starts all services without errors (services may not have full functionality yet) |

**Scope:**
- Finalize `docker-compose.yml` with real service definitions
- Create `frontend/Dockerfile` (Python + Streamlit)
- Create `api/Dockerfile` (Python + FastAPI + uvicorn)
- Create `workers/Dockerfile` (Python + ingestion/ETL deps)
- Create `reverse-proxy/Caddyfile` (local dev version)
- Health check definitions
- Network and volume configuration

---

## Phase 1: Data Pipeline

### WI-04: OpenAQ API Client & Ingestion Worker
| Field | Value |
|---|---|
| Azure DevOps | Issue #52 |
| Status | Done |
| Dependencies | WI-02 |
| Inputs | OpenAQ API docs (context registry §4), OLTP schema (§5) |
| Outputs | `workers/ingest.py` — working ingestion script |
| Acceptance | Running `python ingest.py --initial` fetches Budapest locations+sensors+measurements and inserts into staging/oltp tables. IngestionRunLog is populated. |

**Scope:**
- OpenAQ API v3 client class (locations, sensors, parameters, measurements endpoints)
- Pagination handling (OpenAQ API v3 uses `page` and `limit`)
- Error handling + retry logic
- Insert raw data into staging tables
- Upsert locations/sensors/parameters into OLTP tables
- Insert measurements into MeasurementRaw
- Log every run in IngestionRunLog (start, end, status, record counts, errors)
- CLI interface: `--initial` for full historical load, `--incremental` for delta
- Configurable scope (city list, parameter list, date range)

---

### WI-05: Operational Database Tables (OLTP Layer)
| Field | Value |
|---|---|
| Azure DevOps | Issue #57 |
| Status | Done |
| Dependencies | WI-02 |
| Inputs | Table designs from context registry §5 |
| Outputs | Refined SQL DDL with all constraints, sample data verification |
| Acceptance | All tables exist with correct FKs, can insert test data, constraints enforced |

**Note:** This overlaps with WI-02 but focuses on refinement — adding CHECK constraints, DEFAULT values, and verifying the schema works with realistic data. If WI-02 creates the tables fully, this becomes a validation/polish step.

---

### WI-06: Incremental Load & Scheduling
| Field | Value |
|---|---|
| Azure DevOps | Issue #53 |
| Status | Done |
| Dependencies | WI-04 |
| Inputs | Working ingestion script |
| Outputs | Incremental mode working, scheduler config |
| Acceptance | Running `--incremental` only fetches new data since last successful run. Cron entry or scheduler config documented. |

**Scope:**
- Query IngestionRunLog for last successful timestamp
- Pass `date_from` parameter to OpenAQ API
- Deduplication logic (don't insert measurements already present)
- Create `scripts/run_pipeline.sh` that chains: ingest → ETL → predict
- Document cron schedule (every 3 hours for ingestion)

---

## Phase 2A: DBMS Layer

### WI-07: Threshold Alert Business Process
| Field | Value |
|---|---|
| Azure DevOps | Issue #58 |
| Status | Done |
| Dependencies | WI-04, WI-05 |
| Inputs | ThresholdRule table, MeasurementRaw table |
| Outputs | Working alert generation logic |
| Acceptance | When a measurement exceeds a threshold, a PollutionAlert row is created with correct level and status='Open' |

**Scope:**
- Define default threshold rules for PM2.5 (Low/Moderate/High/Critical boundaries)
- Alert generation function: check new measurements against active thresholds
- Create alerts with appropriate risk level
- Can be in Python (application logic) or SQL trigger (see WI-08)
- Status workflow: Open → Reviewed → Closed

---

### WI-08: Database Triggers & Loose Coupling
| Field | Value |
|---|---|
| Azure DevOps | Issue #59 |
| Status | Done |
| Dependencies | WI-05 |
| Inputs | OLTP tables, alert business logic |
| Outputs | PostgreSQL trigger functions |
| Acceptance | INSERT into MeasurementRaw fires trigger, creates alert if threshold exceeded. Audit log populated. |

**Scope:**
- `AFTER INSERT` trigger on MeasurementRaw
- Trigger function checks ThresholdRule, inserts PollutionAlert if exceeded
- Audit trigger on PollutionAlert (log status changes to audit schema)
- Demonstrate loose coupling pattern: trigger → log table → separate job reads log

---

### WI-09: Transactions & Error Handling
| Field | Value |
|---|---|
| Azure DevOps | Issue #60 |
| Status | Done |
| Dependencies | WI-04 |
| Inputs | Ingestion and alert code |
| Outputs | Transaction-wrapped database operations |
| Acceptance | Failed mid-ingestion leaves DB in consistent state (no partial batches). Transaction boundaries documented. |

**Scope:**
- Wrap ingestion batches in transactions (commit per batch, rollback on error)
- Alert generation within transaction boundary
- Demonstrate savepoints for partial success scenarios
- Error handling: log errors, don't crash the pipeline

---

### WI-10: FastAPI Backend
| Field | Value |
|---|---|
| Azure DevOps | Issue #61 |
| Status | Done |
| Dependencies | WI-02 |
| Inputs | Database schema, required endpoints |
| Outputs | `api/main.py` with all routes, working Swagger UI |
| Acceptance | `GET /health` returns 200, `GET /locations` returns data, Swagger at /docs works |

**Scope:**
- FastAPI app with routers: health, locations, measurements, alerts, predictions
- Database connection (asyncpg or psycopg2 + connection pool)
- Pydantic response models
- `GET /health` — DB connectivity check
- `GET /locations` — list monitored locations
- `GET /measurements?city=&parameter=&date_from=&date_to=` — filtered measurements
- `GET /alerts?status=` — list alerts
- `GET /predictions?location=` — latest predictions
- `POST /demo/refresh` — trigger pipeline (protected)
- CORS configuration for frontend

---

### WI-11: Streamlit Operational GUI
| Field | Value |
|---|---|
| Azure DevOps | Issue #62 |
| Status | Done |
| Dependencies | WI-10 |
| Inputs | FastAPI endpoints |
| Outputs | Multi-page Streamlit app |
| Acceptance | Can view stations, measurements, manage thresholds, view alerts through the GUI |

**Scope:**
- Page 1: Overview (latest measurements, active alerts, worst station)
- Page 2: Station Explorer (select city/station, view sensor data, time series)
- Page 3: Threshold Management (view/add/edit threshold rules)
- Page 4: Alerts (list alerts, filter by status/level, mark reviewed)
- Page 5: System Status (ingestion logs, pipeline health)
- Calls FastAPI backend (not direct DB access)

---

### WI-12: Columnstore/Indexing & Partitioning
| Field | Value |
|---|---|
| Azure DevOps | Issue #63 |
| Status | Done |
| Dependencies | WI-05 |
| Inputs | Tables with data |
| Outputs | Applied indexes and partitioning |
| Acceptance | BRIN index on MeasurementRaw datetime, table partitioning by month on MeasurementRaw, EXPLAIN shows index usage |

**Scope:**
- BRIN index on `MeasurementRaw.measurement_datetime` (PostgreSQL equivalent of columnstore for time-series)
- B-tree indexes on FK columns
- Table partitioning: `MeasurementRaw` partitioned by month (PARTITION BY RANGE)
- Document index choices and rationale (for the report)
- Benchmark query with/without indexes (simple EXPLAIN ANALYZE comparison)

---

### WI-13: Backup & Maintenance Jobs
| Field | Value |
|---|---|
| Azure DevOps | Issue #64 |
| Status | Blocked (needs WI-02) |
| Dependencies | WI-02 |
| Inputs | Running PostgreSQL container |
| Outputs | `scripts/backup_db.sh`, documented maintenance plan |
| Acceptance | Backup script creates dump file, retains 7 days. VACUUM/REINDEX commands documented. |

**Scope:**
- `scripts/backup_db.sh` — pg_dump with timestamp, retention policy (keep 7)
- Document maintenance tasks: VACUUM ANALYZE, REINDEX
- Cron entry for daily backup
- Restore procedure documented
- Optional: backup verification (restore to temp DB and check)

---

## Phase 2B: Data Warehouse Layer

### WI-14: Star Schema Design & DW Tables
| Field | Value |
|---|---|
| Azure DevOps | Issue #65 |
| Status | Blocked (needs WI-02) |
| Dependencies | WI-02 |
| Inputs | DW schema from context registry §5 |
| Outputs | Refined DDL, ER diagram |
| Acceptance | All DW tables created with surrogate keys, dimension tables have SCD2 fields where applicable |

**Scope:**
- Verify/refine `003_create_dw_tables.sql`
- Surrogate key strategy (SERIAL or BIGSERIAL)
- DimDate populated for relevant date range (e.g., 2024-01-01 to 2026-12-31)
- DimTime populated (24 hours × optional granularity)
- DimRiskClass seeded (Low, Moderate, High, Critical with bounds)
- Generate ER diagram (for report)

---

### WI-15: ETL Pipeline (Staging → DW)
| Field | Value |
|---|---|
| Azure DevOps | Issue #66 |
| Status | Blocked (needs WI-04, WI-14) |
| Dependencies | WI-04, WI-14 |
| Inputs | Populated staging/OLTP tables, empty DW tables |
| Outputs | `workers/etl.py` |
| Acceptance | Running `python etl.py` transforms staging data into DW facts+dimensions. FactAirQualityMeasurement populated with correct dimension keys. |

**Scope:**
- Load/update DimLocation from OLTP Location table
- Load/update DimSensor from OLTP Sensor table
- Load/update DimParameter from OLTP Parameter table
- Map measurements to dimension surrogate keys
- Classify each measurement (assign risk_class_key)
- Insert into FactAirQualityMeasurement
- Generate FactPollutionAlert from PollutionAlert table
- Incremental: only process measurements not yet in DW (track high-water mark)
- Data quality checks: reject NULL values, out-of-range values

---

### WI-16: SCD2 Implementation
| Field | Value |
|---|---|
| Azure DevOps | Issue #67 |
| Status | Blocked (needs WI-15) |
| Dependencies | WI-15 |
| Inputs | DimLocation with valid_from/valid_to/is_current fields |
| Outputs | SCD2 logic in ETL |
| Acceptance | When a location's metadata changes (e.g., name update), old row gets valid_to set, new row inserted with is_current=True. Historical facts still point to old dimension key. |

**Scope:**
- Detect changes in location attributes (compare source vs current dimension row)
- If changed: expire current row (set valid_to, is_current=False), insert new version
- If new: insert with valid_from=today, valid_to=NULL, is_current=True
- If unchanged: no action
- Apply same logic to DimSensor if time permits
- Test with a simulated metadata change

---

### WI-17: Risk Classification (Rule-Based & ML)
| Field | Value |
|---|---|
| Azure DevOps | Issue #68 |
| Status | Blocked (needs WI-15) |
| Dependencies | WI-15 |
| Inputs | Measurement data in DW |
| Outputs | Classification logic, populated risk_class_key in facts |
| Acceptance | Every FactAirQualityMeasurement has a valid risk_class_key based on PM2.5 thresholds |

**Scope:**
- Rule-based classifier function: value → risk class (using thresholds from context registry §10)
- Apply during ETL (each measurement gets classified)
- Optional ML classifier (train on labeled data if enough historical data)
- Store classification results in fact table
- Summary statistics: % of measurements in each risk class

---

### WI-18: PM2.5 Prediction Model
| Field | Value |
|---|---|
| Azure DevOps | Issue #69 |
| Status | Blocked (needs WI-15) |
| Dependencies | WI-15 |
| Inputs | Historical measurements in DW |
| Outputs | `workers/train_model.py`, `workers/predict.py`, model artifact |
| Acceptance | Model trained on historical data, predicts next-hour PM2.5 with documented MAE/RMSE. Predictions stored in FactPrediction. |

**Scope:**
- Feature engineering in `train_model.py`:
  - Current PM2.5 value
  - Previous hour PM2.5
  - Rolling 3h and 6h averages
  - Hour of day, day of week, is_weekend, month
  - Station/location (encoded)
- Train/test split (80/20 chronological)
- Train Linear Regression baseline + Random Forest
- Evaluate: MAE, RMSE, R²
- Save model artifact (joblib/pickle)
- `predict.py`: load model, generate predictions for next hour, insert into FactPrediction
- Classify predicted value into risk class

---

### WI-19: Dashboard
| Field | Value |
|---|---|
| Azure DevOps | Issue #70 |
| Status | Blocked (needs WI-15) |
| Dependencies | WI-15, WI-18 (partial — can start without predictions) |
| Inputs | DW tables populated, FastAPI serving data |
| Outputs | Multi-page analytical dashboard |
| Acceptance | 4 dashboard pages showing trends, risk periods, predictions, and data ops. Filters working. |

**Scope:**
- Page 1 — Air Quality Overview: latest values, trend charts, worst station, avg this week
- Page 2 — High-Risk Periods: heatmap (hour × weekday), alerts by pollutant/station
- Page 3 — Prediction: actual vs predicted line chart, predicted risk, model error
- Page 4 — Data Operations: ingestion runs, records/day, failed runs, missing periods
- Filters: city, station, pollutant, date range
- KPI cards at top of overview
- Can be Streamlit pages or separate Power BI/Looker Studio (Streamlit primary)

---

### WI-20: Automated DW Refresh
| Field | Value |
|---|---|
| Azure DevOps | Issue #71 |
| Status | Blocked (needs WI-06, WI-15, WI-18) |
| Dependencies | WI-06, WI-15, WI-18 |
| Inputs | All pipeline components working |
| Outputs | End-to-end automated pipeline |
| Acceptance | Single script or scheduled job runs: ingest → ETL → predict → dashboard shows new data |

**Scope:**
- `scripts/run_pipeline.sh`: orchestrates full pipeline run
- Error handling: if ingestion fails, skip ETL; if ETL fails, skip predict
- Logging: pipeline run status
- Cron schedule: every 3 hours for ingest+ETL, daily for prediction
- Verify with a demo: trigger pipeline, see dashboard update

---

## Phase 3: Deployment

### WI-21: Cloud Deployment (Oracle Cloud VM)
| Field | Value |
|---|---|
| Azure DevOps | Issue #55 |
| Status | Blocked (needs Phase 2 substantially complete) |
| Dependencies | WI-03 (Docker Compose working locally) |
| Inputs | Deployment docs from context registry, working docker-compose |
| Outputs | System running at mw79on-demo.online |
| Acceptance | https://mw79on-demo.online shows dashboard, https://api.mw79on-demo.online/docs shows Swagger |

**Scope:**
- Provision Oracle Cloud VM (or alternative VPS)
- Install Docker, configure UFW
- Clone repo, create .env
- Set up Caddy with production Caddyfile
- Configure Cloudflare DNS (A records → VM IP)
- `docker compose up -d --build`
- Run initial data load
- Verify public access + HTTPS

---

### WI-22: CI/CD Pipeline (GitHub Actions)
| Field | Value |
|---|---|
| Azure DevOps | Issue #56 |
| Status | Blocked (needs WI-21) |
| Dependencies | WI-21 |
| Inputs | Working deployment, SSH access |
| Outputs | `.github/workflows/deploy.yml` |
| Acceptance | Push to main → GitHub Actions → deploys to VM → health check passes |

**Scope:**
- Generate SSH deploy key
- Configure GitHub secrets (SSH_HOST, SSH_USER, SSH_PRIVATE_KEY, etc.)
- Workflow: checkout → optional tests → SSH deploy → health check
- Manual trigger option (workflow_dispatch)

---

## Phase 4: Documentation & Presentation

### WI-23: Architecture Diagrams
| Field | Value |
|---|---|
| Azure DevOps | Issue #76 |
| Status | Ready (can start anytime) |
| Dependencies | None (refine as system develops) |
| Inputs | Architecture from context registry, deployment docs |
| Outputs | `diagrams/` — architecture diagram in PDF/PNG |
| Acceptance | Professional boxes-and-arrows diagram showing OLTP → ETL → DW → Analytics, with technology labels |

**Scope:**
- Main system architecture (3-layer diagram with tech labels)
- Data flow diagram (OpenAQ → staging → OLTP → DW → dashboard)
- Star schema ER diagram
- Deployment architecture (Docker, Caddy, Cloudflare, Oracle Cloud)
- Tool: draw.io, PlantUML, Mermaid, or TikZ

---

### WI-24: DBMS Course PDF
| Field | Value |
|---|---|
| Azure DevOps | Issue #72 |
| Status | Blocked (needs Phase 2A substantially complete) |
| Dependencies | WI-07 through WI-13, WI-23 |
| Inputs | Working system, architecture diagram, LaTeX template (context registry §9) |
| Outputs | `reports/dbms/report.tex` → `reports/dbms/report.pdf` |
| Acceptance | ≥2 pages, contains: team name, members, architecture diagram, functional spec (bulleted), logical data model |

**Scope:**
- Use article template from context registry §9
- Section 1: Team info
- Section 2: Architecture diagram (emphasis on OLTP layer, triggers, transactions, GUI)
- Section 3: Functional specification (bulleted list of features)
- Section 4: Logical data model (OLTP ER diagram or table list)
- Section 5: Technologies used (PostgreSQL, FastAPI, Streamlit, Docker, triggers, transactions, partitioning)
- Keep it concise but complete (2–4 pages)

---

### WI-25: DW Course PDF
| Field | Value |
|---|---|
| Azure DevOps | Issue #73 |
| Status | Blocked (needs Phase 2B substantially complete) |
| Dependencies | WI-14 through WI-20, WI-23 |
| Inputs | Working system, architecture diagram, LaTeX template |
| Outputs | `reports/dw/report.tex` → `reports/dw/report.pdf` |
| Acceptance | ≥2 pages, contains: team name, members, architecture diagram, functional spec, logical data model (star schema) |

**Scope:**
- Use article template from context registry §9
- Section 1: Team info
- Section 2: Architecture diagram (emphasis on ETL, staging, DW, dashboard)
- Section 3: Functional specification (bulleted: ingestion, ETL, SCD2, classification, prediction, dashboard)
- Section 4: Logical data model (star schema diagram — facts + dimensions)
- Section 5: Technologies used (PostgreSQL, Python ETL, scikit-learn, Streamlit/Power BI, Docker)
- Keep it concise but complete (2–4 pages)

---

### WI-26: DBMS Presentation Slides & Demo Script
| Field | Value |
|---|---|
| Azure DevOps | Issue #74 |
| Status | Blocked (needs WI-24) |
| Dependencies | WI-24, system working |
| Inputs | DBMS demo script from context registry §11, working system |
| Outputs | `slides/dbms/slides.tex` → `slides/dbms/slides.pdf` |
| Acceptance | ~10–12 Beamer slides covering intro, architecture, demo walkthrough, conclusion |

**Scope:**
- Slide 1: Title (project name, team, course)
- Slide 2: Problem statement / motivation
- Slide 3: Architecture overview (diagram)
- Slide 4: Technologies used
- Slides 5–9: Demo walkthrough (GUI, thresholds, alerts, triggers, transactions, logs)
- Slide 10: Deployment & DevOps
- Slide 11: Summary / lessons learned
- Speaker notes with demo script timing

---

### WI-27: DW Presentation Slides & Demo Script
| Field | Value |
|---|---|
| Azure DevOps | Issue #75 |
| Status | Blocked (needs WI-25) |
| Dependencies | WI-25, system working |
| Inputs | DW demo script from context registry §11, working system |
| Outputs | `slides/dw/slides.tex` → `slides/dw/slides.pdf` |
| Acceptance | ~10–12 Beamer slides covering intro, star schema, ETL, dashboard, prediction, conclusion |

**Scope:**
- Slide 1: Title (project name, team, course)
- Slide 2: Problem statement / motivation
- Slide 3: Architecture overview (diagram, DW emphasis)
- Slide 4: Star schema design
- Slide 5: ETL pipeline + SCD2
- Slides 6–8: Dashboard demo (overview, risk periods, predictions)
- Slide 9: ML model results (actual vs predicted, metrics)
- Slide 10: Automated refresh & scheduling
- Slide 11: Deployment
- Slide 12: Summary / lessons learned
- Speaker notes with demo script timing

---

## Dependency Graph (Simplified)

```
WI-01 (Scaffolding)
  ├── WI-02 (PostgreSQL) ──┬── WI-04 (Ingestion) ──── WI-06 (Incremental) ──┐
  │                        │        │                                          │
  │                        │        ├── WI-07 (Alerts) ── WI-08 (Triggers)   │
  │                        │        │                                          │
  │                        │        └── WI-09 (Transactions)                  │
  │                        │                                                   │
  │                        ├── WI-05 (OLTP Refine) ── WI-12 (Indexes)        │
  │                        │                                                   │
  │                        ├── WI-10 (FastAPI) ── WI-11 (Streamlit GUI)      │
  │                        │                                                   │
  │                        ├── WI-13 (Backup)                                 │
  │                        │                                                   │
  │                        └── WI-14 (Star Schema) ── WI-15 (ETL) ──┬── WI-16 (SCD2)
  │                                                                  ├── WI-17 (Classification)
  │                                                                  ├── WI-18 (Prediction)
  │                                                                  └── WI-19 (Dashboard)
  │                                                                           │
  └── WI-03 (Docker) ─────────────────────── WI-21 (Deploy) ── WI-22 (CI/CD)│
                                                                              │
                                              WI-20 (Auto Refresh) ───────────┘
                                                        │
                                              WI-23 (Diagrams) ─── WI-24 (DBMS PDF) ── WI-26 (DBMS Slides)
                                                        │
                                                        └────────── WI-25 (DW PDF) ── WI-27 (DW Slides)
```

---

## Work Item Size Estimates

| Size | Work Items | Typical Context Needed |
|---|---|---|
| Small (single file, <100 lines) | WI-01, WI-13, WI-23 | Just this plan + context registry |
| Medium (2–4 files, core logic) | WI-02, WI-03, WI-05, WI-06, WI-07, WI-08, WI-09, WI-12, WI-14, WI-16, WI-17, WI-22, WI-24, WI-25, WI-26, WI-27 | Plan + registry + 1–2 existing files |
| Large (multi-file, complex logic) | WI-04, WI-10, WI-11, WI-15, WI-18, WI-19, WI-20, WI-21 | Plan + registry + multiple existing files |

For large items, consider splitting into sub-tasks on the Azure DevOps board if they prove too big for one session.
