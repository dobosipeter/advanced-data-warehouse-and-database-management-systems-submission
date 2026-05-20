# Context Registry

## Purpose

This document records **what is found where** across all relevant locations for the Air Quality Intelligence System project. Any agent working on this project should read this file first to orient itself without needing to re-explore the entire filesystem.

---

## 1. Repository Locations

### Submission Repository (Working Repo)
```
~/git/advanced-data-warehouse-and-database-management-systems-submission/
├── .github/
│   └── workflows/
├── .git/
├── .gitignore
├── .env.example
├── docker-compose.yml
├── README.md
├── api/
├── database/
├── diagrams/
├── docs/
│   ├── 00-master-plan.md          ← Orchestrator plan (this project)
│   ├── 01-context-registry.md     ← THIS FILE
│   └── 02-implementation-plan.md  ← Detailed work items
├── frontend/
├── reports/
├── reverse-proxy/
├── scripts/
├── slides/
├── tests/
└── workers/
```

### Planning & Requirements (Read-Only Reference)
```
~/university/dbanddw/
├── assessment.md                              ← CRITICAL: Course requirements, rubrics, deadlines, overlap analysis
├── air_quality_project_plan.md                ← High-level project plan & architecture
├── air_quality_project_detailed_description.md ← Full functional spec, DB schemas, DW schemas, ETL plan, ML plan
├── air_quality_deployment_description.md      ← Deployment architecture (Docker, Oracle Cloud, domain, services)
├── air_quality_deployment_plan_cicd.md        ← Step-by-step deployment & CI/CD instructions
└── personal_use_case_ideas                    ← Personal use case: holiday air quality forecasting
```

### LaTeX Template Reference
```
~/git/advanced-image-processing-methods/
├── homework_1/REPORT.tex    ← Simple LaTeX article template (use as style reference)
├── homework_2/REPORT.tex
├── homework_3/REPORT.tex
├── homework_4/REPORT.tex
├── homework_5/REPORT.tex
└── homework_6/REPORT.tex
```
**Template style:** `article` class, 11pt, A4, 1in margins, packages: geometry, fontenc(T1), inputenc(utf8), graphicx, hyperref, enumitem, float. Author: Peter Dobosi.

---

## 2. Course Requirements Summary

### Both Courses (Common)
- **Instructor:** István Vassányi
- **Project weight:** 50% of grade each
- **Team size:** 1 or 2
- **Demo:** ~10 min, live demo or screencast
- **Documentation:** ≥2-page PDF with: team name, members, boxes-and-arrows architecture diagram (technologies named), bulleted functional spec, logical data model
- **Upload:** ≥2 days before review
- **Peer-vote bonus:** up to +15 points
- **PDF filename:** = team name

### DW Course Specifics
- **Minimum:** Working data-processing IS that loads/refreshes a DW from OLTP source and analyzes/visualizes automatically
- **100% target:** Reports, automated refresh, SCD2, ML models, polished GUI
- **Key topics to demonstrate:** Star/snowflake schema, staging area, ETL, SCD2, CDC, OLAP, Power BI/Looker Studio, columnstore indexes

### DBMS Course Specifics
- **Minimum:** Working IS with GUI supporting at least one business process, using ≥1 course technology
- **100% target:** Server-side features (transactions, logging, backups), high-quality GUI, complex business processes, integration of multiple technologies
- **Key topics to demonstrate:** Triggers, jobs, transactions, replication/HA concepts, columnstore/partitioning, graph/document stores, in-memory, backups, alerts

---

## 3. Technology Stack (Decided)

| Component | Technology | Notes |
|---|---|---|
| Database | PostgreSQL 16 | Docker container, schemas: staging, oltp, dw, ml, audit |
| Backend API | FastAPI (Python) | REST endpoints, Swagger auto-docs |
| Frontend/GUI | Streamlit | Interactive dashboard + operational GUI |
| ETL | Python scripts | Custom ETL in workers/ directory |
| ML | scikit-learn | Linear Regression / Random Forest for PM2.5 prediction |
| Containerization | Docker Compose | All services containerized |
| Reverse Proxy | Caddy | Auto HTTPS, simple config |
| Hosting | Hetzner Cloud VM (Ubuntu) | Paid VPS fallback after Oracle signup failed |
| DNS/CDN | Namecheap DNS | Domain currently managed directly at registrar |
| Domain | mw79on-demo.online | Purchased, for public demo |
| CI/CD | GitHub Actions | SSH deploy to Hetzner VM |
| Reports | LaTeX (article class) | 2-page PDFs per course |
| Slides | LaTeX (Beamer) | 10-min presentation per course |
| Project tracking | Azure DevOps | https://dev.azure.com/dop3bp/AirQualityIntelligence |

### Database Choice Rationale

PostgreSQL 16 was selected as the primary database because it gives the project one engine that can credibly support both halves of the combined submission:

- OLTP features for the DBMS course: transactions, constraints, triggers, functions, logging tables, JSONB staging payloads, backups, and operational indexes.
- DW features for the warehouse course: separate staging/OLTP/DW schemas, star-schema tables, SCD2-friendly dimensions, BRIN indexes for time-series facts, materialized views if needed, and enough analytical SQL for the demo scope.
- Practical delivery: first-class Docker support, no license or cloud dependency, easy local reproduction, and straightforward deployment on the Hetzner Cloud VM.
- Portfolio value: PostgreSQL is widely used in production, so the implementation remains realistic rather than only matching a classroom tool.

Alternatives considered:

| Alternative | Strengths | Why not primary |
|---|---|---|
| SQL Server | Strong alignment with course topics such as SQL Server Agent, SSIS, columnstore indexes, partitioning, and triggers | Heavier local/container footprint, licensing/platform friction, less convenient for the Linux-first Hetzner deployment |
| MySQL/MariaDB | Simple Docker setup, common OLTP engine | Weaker fit for DW features, SCD2/reporting patterns, analytical indexing, and JSON staging compared with PostgreSQL |
| SQLite | Extremely simple and zero-service local development | Not a realistic server DBMS for transactions, concurrent ingestion/API access, scheduled jobs, backups, or DW demonstration |
| DuckDB | Excellent embedded analytical engine for columnar analytics | Not suitable as the main operational database with concurrent API/GUI writes, triggers, alerts, and long-running service deployment |
| BigQuery | Excellent managed warehouse and course-relevant cloud analytics | Adds cloud cost/setup/auth complexity and does not cover the OLTP/DBMS layer by itself |
| Firestore | Useful for demonstrating document-store concepts | Does not naturally support the relational OLTP plus star-schema DW flow required for the core project |

SQL Server remains a defensible alternative if strict course-technology alignment becomes more important than portability. For now, PostgreSQL gives the best balance of implementability, demo reliability, and coverage across both courses.

---

## 4. Data Source: OpenAQ API

- **Base URL:** https://api.openaq.org/v3/
- **Key endpoints:**
  - `GET /locations` — monitoring stations
  - `GET /locations/{id}/sensors` — sensors at a location
  - `GET /parameters` — pollutant types
  - `GET /sensors/{id}/measurements` — historical measurements
  - `GET /locations/{id}/latest` — latest values
- **Scope:** Budapest (primary), optionally Vienna and Berlin
- **Default Budapest bbox:** `18.9250,47.3494,19.3340,47.6130`
- **Pollutants:** PM2.5, PM10, NO₂, O₃
- **Historical window:** 3–6 months
- **Rate limits:** Check API docs; may need API key for higher limits
- **API Key env var:** `OPENAQ_API_KEY`
- **Pagination:** OpenAQ API v3 uses `page` and `limit` query parameters.

---

## 5. Database Schema Overview

### Staging Schema (`staging`)
- Raw API responses, semi-structured measurement data

### OLTP Schema (`oltp`)
| Table | Purpose |
|---|---|
| `Location` | Monitored stations (openaq_location_id, name, city, country, lat/lon, is_active) |
| `Sensor` | Sensors per location (openaq_sensor_id, location_id FK, parameter_id FK, unit) |
| `Parameter` | Pollutant types (PM2.5, PM10, NO₂, O₃) |
| `MeasurementRaw` | Raw measurements (sensor_id, datetime, value, unit, ingestion_run_id) |
| `ThresholdRule` | Alert thresholds (parameter_id, city, warning_level, min_value) |
| `PollutionAlert` | Generated alerts (measurement_id, threshold_id, alert_level, status) |
| `IngestionRunLog` | Ingestion job metadata (start/end time, status, records inserted, errors) |

### DW Schema (`dw`)
| Table | Type | Purpose |
|---|---|---|
| `FactAirQualityMeasurement` | Fact | Main analytical fact — measurement values with dimension keys |
| `FactPollutionAlert` | Fact | Alert events for analysis |
| `FactPrediction` | Fact | ML prediction outputs |
| `DimLocation` | Dimension | Location attributes, SCD2 candidate |
| `DimSensor` | Dimension | Sensor attributes, SCD2 candidate |
| `DimParameter` | Dimension | Pollutant info |
| `DimDate` | Dimension | Calendar (year, month, day, weekday, is_weekend) |
| `DimTime` | Dimension | Time-of-day (hour, minute, part_of_day) |
| `DimRiskClass` | Dimension | Risk classification categories |

### ML Schema (`ml`)
- Model metadata, training runs, feature stores

### Audit Schema (`audit`)
- `pollution_alert_outbox` event log for trigger-generated alert events; downstream jobs can read unprocessed rows for notifications, integrations, or audit review
- Change logs, data lineage

---

## 6. Project File Structure (Target)

```
advanced-data-warehouse-and-database-management-systems-submission/
├── .github/
│   └── workflows/
│       └── deploy.yml
├── docker-compose.yml
├── docker-compose.prod.yml          (production overrides)
├── .env.example
├── .gitignore
├── README.md
├── frontend/
│   ├── Dockerfile
│   ├── app.py                       (Streamlit main)
│   ├── pages/                       (multi-page Streamlit)
│   └── pyproject.toml
├── api/
│   ├── Dockerfile
│   ├── main.py                      (FastAPI app)
│   ├── routers/
│   ├── models/
│   └── pyproject.toml
├── workers/
│   ├── Dockerfile
│   ├── ingest.py                    (OpenAQ ingestion)
│   ├── etl.py                       (Staging → DW transform)
│   ├── train_model.py               (ML training)
│   ├── predict.py                   (Generate predictions)
│   └── pyproject.toml
├── database/
│   ├── init/
│   │   ├── 001_create_schemas.sql
│   │   ├── 002_create_oltp_tables.sql
│   │   ├── 003_create_dw_tables.sql
│   │   ├── 004_create_indexes.sql
│   │   └── 005_seed_parameters.sql
│   └── migrations/                  (if needed)
├── reverse-proxy/
│   └── Caddyfile
├── scripts/
│   ├── backup_db.sh
│   ├── run_pipeline.sh
│   └── air_quality_pipeline.crontab
├── reports/
│   ├── dbms/
│   │   ├── report.tex
│   │   └── report.pdf
│   └── dw/
│       ├── report.tex
│       └── report.pdf
├── slides/
│   ├── dbms/
│   │   ├── slides.tex
│   │   └── slides.pdf
│   └── dw/
│       ├── slides.tex
│       └── slides.pdf
├── diagrams/
│   └── architecture.drawio          (or .puml / .mmd)
├── docs/
│   ├── 00-master-plan.md
│   ├── 01-context-registry.md
│   └── 02-implementation-plan.md
└── tests/
    ├── test_ingestion.py
    ├── test_etl.py
    └── test_api.py
```

---

## 7. Azure DevOps Board Structure

**Organization:** https://dev.azure.com/dop3bp/  
**Project:** AirQualityIntelligence  
**Process:** Basic (Epic → Issue → Task)

### Epics
| ID | Title |
|---|---|
| #46 | Shared Infrastructure & Data Ingestion |
| #47 | Advanced DBMS Course Deliverable |
| #48 | Advanced Data Warehouse Course Deliverable |
| #49 | Documentation & Presentation |

### Issues (see 02-implementation-plan.md for full breakdown)
- #50–#56 under Epic #46 (Infrastructure)
- #57–#64 under Epic #47 (DBMS)
- #65–#71 under Epic #48 (DW)
- #72–#76 under Epic #49 (Docs)

---

## 8. Deployment Details

| Item | Value |
|---|---|
| Domain | mw79on-demo.online |
| Public URLs | https://mw79on-demo.online (dashboard), https://api.mw79on-demo.online/docs (API) |
| VM target | Hetzner Cloud Ubuntu 24.04, ≥4GB RAM |
| Ports exposed | 22 (SSH), 80 (HTTP), 443 (HTTPS) |
| PostgreSQL port | 5432 (internal only, not exposed) |
| Docker volume | postgres_data (persistent) |
| Backup | Daily pg_dump, keep 7 days |
| Secrets location | Server-side .env + GitHub Actions secrets |

---

## 9. LaTeX Style Reference

Based on `~/git/advanced-image-processing-methods/homework_1/REPORT.tex`:

```latex
\documentclass[11pt,a4paper]{article}
\usepackage[margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{float}

\title{...}
\author{Peter Dobosi}
\date{\today}
```

For slides, use Beamer with matching style. Add packages as needed: `booktabs`, `tikz`, `listings`, `xcolor`.

---

## 10. Risk Classification Thresholds

| PM2.5 Value (µg/m³) | Risk Class |
|---:|---|
| 0–10 | Low |
| 10–25 | Moderate |
| 25–50 | High |
| 50+ | Critical |

---

## 11. Demo Scripts (High-Level)

### DW Demo (~10 min)
1. Open dashboard → show filters (city, pollutant, date)
2. Show historical pollution trends
3. Drill into a KPI (worst station, peak hours)
4. Show star schema (ER diagram or table view)
5. Trigger ETL or show scheduled job
6. Show staging data → transformed fact table
7. Show SCD2 version history
8. Show prediction vs actual chart
9. Show architecture diagram

### DBMS Demo (~10 min)
1. Open operational GUI (Streamlit)
2. Show monitored stations + latest measurements
3. Add/edit a pollution threshold rule
4. Trigger ingestion or insert measurement
5. Show alert being generated (trigger fires)
6. Show ingestion logs + transaction handling
7. Show indexes, partitioning, backup job
8. Show Docker containers / deployment
9. Show architecture diagram (same, different emphasis)

---

## 12. External References

- OpenAQ API docs: https://docs.openaq.org/
- OpenAQ API v3: https://api.openaq.org/v3/
- Oracle Cloud Free Tier: https://www.oracle.com/cloud/free/
- Cloudflare Free Plan: https://www.cloudflare.com/plans/free/
- Course notes (DW): `~/university/dbanddw/` references `datawarehouse/DW_jegyzet_MSc_2026.pdf`
- Course notes (DBMS): `~/university/dbanddw/` references `database/jegyzet_haladó_AB_Vassányi_István_2026.pdf`
- Azure DevOps Board: https://dev.azure.com/dop3bp/AirQualityIntelligence/_boards
