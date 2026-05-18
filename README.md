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
   - API docs: http://localhost:8000/docs

The first implementation phase creates the scaffold. Database schemas, ingestion logic, ETL, and dashboards are added by later work items.
