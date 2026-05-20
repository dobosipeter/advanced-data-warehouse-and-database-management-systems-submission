from __future__ import annotations

import os
import shlex
import subprocess
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, Iterator

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict
from psycopg.rows import dict_row


class Settings(BaseSettings):
    database_url: str = "postgresql://air_quality:change-me@db:5432/air_quality"
    cors_allow_origins: str = "http://localhost:8501,http://frontend:8501"
    demo_refresh_token: str | None = None
    demo_refresh_command: str | None = None
    demo_refresh_timeout_seconds: int = 600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]
        return origins or ["*"]


settings = Settings()


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class HealthResponse(APIModel):
    status: str
    database: str


class LocationResponse(APIModel):
    location_id: int
    openaq_location_id: int
    name: str
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    timezone: str | None
    active_sensor_count: int
    latest_measurement_at: datetime | None


class MeasurementResponse(APIModel):
    measurement_id: int
    measured_at: datetime
    value: float
    unit: str
    city: str
    location_name: str
    parameter_code: str
    parameter_name: str
    sensor_id: int
    ingestion_run_id: int | None


class MeasurementSeriesResponse(APIModel):
    measured_hour: datetime
    city: str
    parameter_code: str
    unit: str
    average_value: float
    measurement_count: int


class AlertResponse(APIModel):
    pollution_alert_id: int
    generated_at: datetime
    alert_level: str
    status: str
    measurement_value: float
    measurement_unit: str
    measured_at: datetime
    city: str
    location_name: str
    parameter_code: str
    parameter_name: str
    threshold_value: float
    reviewed_at: datetime | None
    notes: str | None


class AlertUpdateRequest(APIModel):
    status: str
    notes: str | None = None


class ThresholdRuleResponse(APIModel):
    threshold_rule_id: int
    parameter_id: int
    parameter_code: str
    parameter_name: str
    city: str
    warning_level: str
    min_value: float
    is_active: bool
    updated_at: datetime


class ThresholdRuleRequest(APIModel):
    parameter_code: str
    city: str
    warning_level: str
    min_value: float
    is_active: bool = True


class IngestionRunResponse(APIModel):
    ingestion_run_id: int
    run_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_inserted: int
    records_failed: int
    error_message: str | None


class PredictionResponse(APIModel):
    fact_prediction_id: int
    target_measured_at: datetime
    predicted_value: float
    model_name: str
    model_version: str
    city: str
    location_name: str
    parameter_code: str
    created_at: datetime
    risk_class_label: str | None = None
    actual_value: float | None = None
    absolute_error: float | None = None


class DemoRefreshResponse(APIModel):
    status: str
    command: str
    output: str


app = FastAPI(
    title="Air Quality Intelligence API",
    description="Operational and analytical API for the air quality intelligence system.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def open_db_connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def get_db_connection() -> Iterator[psycopg.Connection[Any]]:
    with open_db_connection() as conn:
        yield conn


def fetch_all(
    conn: psycopg.Connection[Any],
    query: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return list(cur.fetchall())


def fetch_one(
    conn: psycopg.Connection[Any],
    query: str,
    params: tuple[Any, ...] = (),
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
        return row


def execute_one(
    conn: psycopg.Connection[Any],
    query: str,
    params: tuple[Any, ...] = (),
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
        conn.commit()
        return row


DBConnection = Annotated[psycopg.Connection[Any], Depends(get_db_connection)]


@app.get("/health", response_model=HealthResponse)
def health(conn: DBConnection) -> HealthResponse:
    try:
        row = fetch_one(conn, "SELECT 'ok' AS status, current_database() AS database")
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc

    return HealthResponse(**row)


@app.get("/locations", response_model=list[LocationResponse])
def list_locations(conn: DBConnection) -> list[LocationResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            l.location_id,
            l.openaq_location_id,
            l.name,
            l.city,
            l.country,
            l.latitude::double precision AS latitude,
            l.longitude::double precision AS longitude,
            l.timezone,
            COUNT(DISTINCT s.sensor_id) FILTER (WHERE s.is_active) AS active_sensor_count,
            MAX(m.measured_at) AS latest_measurement_at
        FROM oltp.location AS l
        LEFT JOIN oltp.sensor AS s
            ON s.location_id = l.location_id
        LEFT JOIN oltp.measurement_raw AS m
            ON m.sensor_id = s.sensor_id
        WHERE l.is_active
        GROUP BY l.location_id
        ORDER BY l.city, l.name
        """,
    )
    return [LocationResponse(**row) for row in rows]


@app.get("/measurements", response_model=list[MeasurementResponse])
def list_measurements(
    conn: DBConnection,
    city: str | None = Query(default=None),
    parameter: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=10000),
) -> list[MeasurementResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            m.measurement_id,
            m.measured_at,
            m.value::double precision AS value,
            m.unit,
            l.city,
            l.name AS location_name,
            p.code AS parameter_code,
            p.display_name AS parameter_name,
            s.sensor_id,
            m.ingestion_run_id
        FROM oltp.measurement_raw AS m
        JOIN oltp.sensor AS s
            ON s.sensor_id = m.sensor_id
        JOIN oltp.location AS l
            ON l.location_id = s.location_id
        JOIN oltp.parameter AS p
            ON p.parameter_id = s.parameter_id
        WHERE (%s::text IS NULL OR l.city = %s)
          AND (%s::text IS NULL OR p.code = %s)
          AND (%s::timestamptz IS NULL OR m.measured_at >= %s)
          AND (%s::timestamptz IS NULL OR m.measured_at <= %s)
        ORDER BY m.measured_at DESC
        LIMIT %s
        """,
        (city, city, parameter, parameter, date_from, date_from, date_to, date_to, limit),
    )
    return [MeasurementResponse(**row) for row in rows]


@app.get("/measurement-series", response_model=list[MeasurementSeriesResponse])
def measurement_series(
    conn: DBConnection,
    city: str | None = Query(default=None),
    parameter: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=10000, ge=1, le=50000),
) -> list[MeasurementSeriesResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            date_trunc('hour', m.measured_at) AS measured_hour,
            l.city,
            p.code AS parameter_code,
            m.unit,
            AVG(m.value)::double precision AS average_value,
            COUNT(*)::integer AS measurement_count
        FROM oltp.measurement_raw AS m
        JOIN oltp.sensor AS s
            ON s.sensor_id = m.sensor_id
        JOIN oltp.location AS l
            ON l.location_id = s.location_id
        JOIN oltp.parameter AS p
            ON p.parameter_id = s.parameter_id
        WHERE (%s::text IS NULL OR l.city = %s)
          AND (%s::text IS NULL OR p.code = %s)
          AND (%s::timestamptz IS NULL OR m.measured_at >= %s)
          AND (%s::timestamptz IS NULL OR m.measured_at <= %s)
        GROUP BY measured_hour, l.city, p.code, m.unit
        ORDER BY measured_hour DESC, l.city, p.code
        LIMIT %s
        """,
        (city, city, parameter, parameter, date_from, date_from, date_to, date_to, limit),
    )
    return [MeasurementSeriesResponse(**row) for row in rows]


@app.get("/alerts", response_model=list[AlertResponse])
def list_alerts(
    conn: DBConnection,
    status_filter: str | None = Query(default=None, alias="status"),
    level: str | None = Query(default=None),
    city: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[AlertResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            a.pollution_alert_id,
            a.generated_at,
            a.alert_level,
            a.status,
            m.value::double precision AS measurement_value,
            m.unit AS measurement_unit,
            m.measured_at,
            l.city,
            l.name AS location_name,
            p.code AS parameter_code,
            p.display_name AS parameter_name,
            tr.min_value::double precision AS threshold_value,
            a.reviewed_at,
            a.notes
        FROM oltp.pollution_alert AS a
        JOIN oltp.measurement_raw AS m
            ON m.measurement_id = a.measurement_id
        JOIN oltp.threshold_rule AS tr
            ON tr.threshold_rule_id = a.threshold_rule_id
        JOIN oltp.sensor AS s
            ON s.sensor_id = m.sensor_id
        JOIN oltp.location AS l
            ON l.location_id = s.location_id
        JOIN oltp.parameter AS p
            ON p.parameter_id = s.parameter_id
        WHERE (%s::text IS NULL OR a.status = %s)
          AND (%s::text IS NULL OR a.alert_level = %s)
          AND (%s::text IS NULL OR l.city = %s)
        ORDER BY a.generated_at DESC
        LIMIT %s
        """,
        (status_filter, status_filter, level, level, city, city, limit),
    )
    return [AlertResponse(**row) for row in rows]


@app.patch("/alerts/{pollution_alert_id}", response_model=AlertResponse)
def update_alert(
    pollution_alert_id: int,
    payload: AlertUpdateRequest,
    conn: DBConnection,
) -> AlertResponse:
    if payload.status not in {"open", "reviewed", "closed"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid alert status.")

    row = execute_one(
        conn,
        """
        WITH updated AS (
            UPDATE oltp.pollution_alert
            SET status = %s,
                notes = COALESCE(%s, notes),
                reviewed_at = CASE
                    WHEN %s IN ('reviewed', 'closed') THEN COALESCE(reviewed_at, now())
                    ELSE reviewed_at
                END
            WHERE pollution_alert_id = %s
            RETURNING *
        )
        SELECT
            a.pollution_alert_id,
            a.generated_at,
            a.alert_level,
            a.status,
            m.value::double precision AS measurement_value,
            m.unit AS measurement_unit,
            m.measured_at,
            l.city,
            l.name AS location_name,
            p.code AS parameter_code,
            p.display_name AS parameter_name,
            tr.min_value::double precision AS threshold_value,
            a.reviewed_at,
            a.notes
        FROM updated AS a
        JOIN oltp.measurement_raw AS m
            ON m.measurement_id = a.measurement_id
        JOIN oltp.threshold_rule AS tr
            ON tr.threshold_rule_id = a.threshold_rule_id
        JOIN oltp.sensor AS s
            ON s.sensor_id = m.sensor_id
        JOIN oltp.location AS l
            ON l.location_id = s.location_id
        JOIN oltp.parameter AS p
            ON p.parameter_id = s.parameter_id
        """,
        (payload.status, payload.notes, payload.status, pollution_alert_id),
    )
    return AlertResponse(**row)


@app.get("/thresholds", response_model=list[ThresholdRuleResponse])
def list_thresholds(
    conn: DBConnection,
    city: str | None = Query(default=None),
    parameter: str | None = Query(default=None),
) -> list[ThresholdRuleResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            tr.threshold_rule_id,
            tr.parameter_id,
            p.code AS parameter_code,
            p.display_name AS parameter_name,
            tr.city,
            tr.warning_level,
            tr.min_value::double precision AS min_value,
            tr.is_active,
            tr.updated_at
        FROM oltp.threshold_rule AS tr
        JOIN oltp.parameter AS p
            ON p.parameter_id = tr.parameter_id
        WHERE (%s::text IS NULL OR tr.city = %s)
          AND (%s::text IS NULL OR p.code = %s)
        ORDER BY tr.city, p.code, tr.min_value
        """,
        (city, city, parameter, parameter),
    )
    return [ThresholdRuleResponse(**row) for row in rows]


@app.post("/thresholds", response_model=ThresholdRuleResponse)
def upsert_threshold(
    payload: ThresholdRuleRequest,
    conn: DBConnection,
) -> ThresholdRuleResponse:
    if payload.warning_level not in {"low", "moderate", "high", "critical"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid warning level.")
    if payload.min_value < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="min_value must be non-negative.")

    row = execute_one(
        conn,
        """
        WITH selected_parameter AS (
            SELECT parameter_id
            FROM oltp.parameter
            WHERE code = %s
        ),
        upserted AS (
            INSERT INTO oltp.threshold_rule (parameter_id, city, warning_level, min_value, is_active)
            SELECT parameter_id, %s, %s, %s, %s
            FROM selected_parameter
            ON CONFLICT (parameter_id, city, warning_level) DO UPDATE
            SET min_value = EXCLUDED.min_value,
                is_active = EXCLUDED.is_active,
                updated_at = now()
            RETURNING *
        )
        SELECT
            tr.threshold_rule_id,
            tr.parameter_id,
            p.code AS parameter_code,
            p.display_name AS parameter_name,
            tr.city,
            tr.warning_level,
            tr.min_value::double precision AS min_value,
            tr.is_active,
            tr.updated_at
        FROM upserted AS tr
        JOIN oltp.parameter AS p
            ON p.parameter_id = tr.parameter_id
        """,
        (payload.parameter_code, payload.city, payload.warning_level, payload.min_value, payload.is_active),
    )
    return ThresholdRuleResponse(**row)


@app.patch("/thresholds/{threshold_rule_id}", response_model=ThresholdRuleResponse)
def update_threshold(
    threshold_rule_id: int,
    payload: ThresholdRuleRequest,
    conn: DBConnection,
) -> ThresholdRuleResponse:
    if payload.warning_level not in {"low", "moderate", "high", "critical"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid warning level.")
    if payload.min_value < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="min_value must be non-negative.")

    row = execute_one(
        conn,
        """
        WITH selected_parameter AS (
            SELECT parameter_id
            FROM oltp.parameter
            WHERE code = %s
        ),
        updated AS (
            UPDATE oltp.threshold_rule AS tr
            SET parameter_id = selected_parameter.parameter_id,
                city = %s,
                warning_level = %s,
                min_value = %s,
                is_active = %s,
                updated_at = now()
            FROM selected_parameter
            WHERE tr.threshold_rule_id = %s
            RETURNING tr.*
        )
        SELECT
            tr.threshold_rule_id,
            tr.parameter_id,
            p.code AS parameter_code,
            p.display_name AS parameter_name,
            tr.city,
            tr.warning_level,
            tr.min_value::double precision AS min_value,
            tr.is_active,
            tr.updated_at
        FROM updated AS tr
        JOIN oltp.parameter AS p
            ON p.parameter_id = tr.parameter_id
        """,
        (
            payload.parameter_code,
            payload.city,
            payload.warning_level,
            payload.min_value,
            payload.is_active,
            threshold_rule_id,
        ),
    )
    return ThresholdRuleResponse(**row)


@app.get("/ingestion-runs", response_model=list[IngestionRunResponse])
def list_ingestion_runs(
    conn: DBConnection,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[IngestionRunResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            ingestion_run_id,
            run_type,
            status,
            started_at,
            finished_at,
            records_inserted,
            records_failed,
            error_message
        FROM oltp.ingestion_run_log
        ORDER BY started_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [IngestionRunResponse(**row) for row in rows]


@app.get("/predictions", response_model=list[PredictionResponse])
def list_predictions(
    conn: DBConnection,
    city: str | None = Query(default=None),
    location: str | None = Query(default=None),
    parameter: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[PredictionResponse]:
    rows = fetch_all(
        conn,
        """
        SELECT
            fp.fact_prediction_id,
            fp.target_measured_at,
            fp.predicted_value::double precision AS predicted_value,
            fp.model_name,
            fp.model_version,
            dl.city,
            dl.name AS location_name,
            dp.code AS parameter_code,
            fp.prediction_created_at AS created_at,
            rc.label AS risk_class_label,
            fam.measurement_value::double precision AS actual_value,
            ABS(fp.predicted_value - fam.measurement_value)::double precision AS absolute_error
        FROM dw.fact_prediction AS fp
        JOIN dw.dim_location AS dl
            ON dl.location_key = fp.location_key
        JOIN dw.dim_parameter AS dp
            ON dp.parameter_key = fp.parameter_key
        LEFT JOIN dw.dim_risk_class AS rc
            ON rc.risk_class_key = fp.risk_class_key
        LEFT JOIN dw.fact_air_quality_measurement AS fam
            ON fam.location_key = fp.location_key
           AND fam.parameter_key = fp.parameter_key
           AND fam.measured_at = fp.target_measured_at
           AND (fp.sensor_key IS NULL OR fam.sensor_key = fp.sensor_key)
        WHERE (%s::text IS NULL OR dl.city = %s)
          AND (%s::text IS NULL OR dl.name = %s)
          AND (%s::text IS NULL OR dp.code = %s)
          AND (%s::timestamptz IS NULL OR fp.target_measured_at >= %s)
          AND (%s::timestamptz IS NULL OR fp.target_measured_at <= %s)
        ORDER BY fp.target_measured_at DESC, fp.prediction_created_at DESC
        LIMIT %s
        """,
        (
            city,
            city,
            location,
            location,
            parameter,
            parameter,
            date_from,
            date_from,
            date_to,
            date_to,
            limit,
        ),
    )
    return [PredictionResponse(**row) for row in rows]


@app.post("/demo/refresh", response_model=DemoRefreshResponse)
def demo_refresh(
    x_demo_token: Annotated[str | None, Header()] = None,
) -> DemoRefreshResponse:
    if settings.demo_refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo refresh is not configured.",
        )
    if x_demo_token != settings.demo_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo refresh token.")
    if not settings.demo_refresh_command:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo refresh command is not configured.",
        )

    try:
        completed = subprocess.run(
            shlex.split(settings.demo_refresh_command),
            capture_output=True,
            text=True,
            timeout=settings.demo_refresh_timeout_seconds,
            check=False,
            env=os.environ.copy(),
        )
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start refresh command: {exc}",
        ) from exc

    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part).strip()
    if completed.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=output or f"Refresh command failed with exit code {completed.returncode}.",
        )

    return DemoRefreshResponse(
        status="started",
        command=settings.demo_refresh_command,
        output=output or "Refresh command completed successfully.",
    )
