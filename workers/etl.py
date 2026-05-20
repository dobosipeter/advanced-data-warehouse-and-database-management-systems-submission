from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import psycopg
from dotenv import load_dotenv


@dataclass(frozen=True)
class ETLResult:
    parameters: int
    locations: int
    sensors: int
    measurements: int
    alerts: int


def database_url_from_env() -> str:
    load_dotenv()
    return os.getenv("DATABASE_URL", "postgresql://air_quality:change-me@db:5432/air_quality")


class ETLRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    def sync_parameters(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dw.dim_parameter (source_parameter_id, code, display_name, unit, is_active)
                SELECT parameter_id, code, display_name, preferred_unit, is_active
                FROM oltp.parameter
                ON CONFLICT (code) DO UPDATE
                SET source_parameter_id = EXCLUDED.source_parameter_id,
                    display_name = EXCLUDED.display_name,
                    unit = EXCLUDED.unit,
                    is_active = EXCLUDED.is_active
                """
            )
            return cur.rowcount

    def sync_locations(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH source_rows AS (
                    SELECT
                        location_id,
                        openaq_location_id,
                        name,
                        city,
                        country,
                        latitude,
                        longitude,
                        first_seen_at,
                        md5(concat_ws('|', openaq_location_id, name, city, country, latitude, longitude)) AS row_hash
                    FROM oltp.location
                    WHERE is_active
                )
                UPDATE dw.dim_location AS current_dim
                SET valid_to = now(),
                    is_current = false
                FROM source_rows AS src
                WHERE current_dim.source_location_id = src.location_id
                  AND current_dim.is_current
                  AND current_dim.row_hash <> src.row_hash
                """
            )
            expired = cur.rowcount

            cur.execute(
                """
                WITH source_rows AS (
                    SELECT
                        location_id,
                        openaq_location_id,
                        name,
                        city,
                        country,
                        latitude,
                        longitude,
                        first_seen_at,
                        md5(concat_ws('|', openaq_location_id, name, city, country, latitude, longitude)) AS row_hash
                    FROM oltp.location
                    WHERE is_active
                )
                INSERT INTO dw.dim_location (
                    source_location_id,
                    openaq_location_id,
                    name,
                    city,
                    country,
                    latitude,
                    longitude,
                    valid_from,
                    valid_to,
                    is_current,
                    row_hash
                )
                SELECT
                    src.location_id,
                    src.openaq_location_id,
                    src.name,
                    src.city,
                    src.country,
                    src.latitude,
                    src.longitude,
                    CASE
                        WHEN existing_any.source_location_id IS NULL THEN COALESCE(src.first_seen_at, now())
                        ELSE now()
                    END,
                    NULL,
                    true,
                    src.row_hash
                FROM source_rows AS src
                LEFT JOIN dw.dim_location AS current_dim
                    ON current_dim.source_location_id = src.location_id
                   AND current_dim.is_current
                LEFT JOIN (
                    SELECT DISTINCT source_location_id
                    FROM dw.dim_location
                ) AS existing_any
                    ON existing_any.source_location_id = src.location_id
                WHERE current_dim.location_key IS NULL
                """
            )
            inserted = cur.rowcount
            return expired + inserted

    def sync_sensors(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH source_rows AS (
                    SELECT
                        sensor_id,
                        openaq_sensor_id,
                        location_id,
                        parameter_id,
                        unit,
                        first_seen_at,
                        md5(concat_ws('|', openaq_sensor_id, location_id, parameter_id, unit)) AS row_hash
                    FROM oltp.sensor
                    WHERE is_active
                )
                UPDATE dw.dim_sensor AS current_dim
                SET valid_to = now(),
                    is_current = false
                FROM source_rows AS src
                WHERE current_dim.source_sensor_id = src.sensor_id
                  AND current_dim.is_current
                  AND current_dim.row_hash <> src.row_hash
                """
            )
            expired = cur.rowcount

            cur.execute(
                """
                WITH source_rows AS (
                    SELECT
                        sensor_id,
                        openaq_sensor_id,
                        location_id,
                        parameter_id,
                        unit,
                        first_seen_at,
                        md5(concat_ws('|', openaq_sensor_id, location_id, parameter_id, unit)) AS row_hash
                    FROM oltp.sensor
                    WHERE is_active
                )
                INSERT INTO dw.dim_sensor (
                    source_sensor_id,
                    openaq_sensor_id,
                    source_location_id,
                    source_parameter_id,
                    unit,
                    valid_from,
                    valid_to,
                    is_current,
                    row_hash
                )
                SELECT
                    src.sensor_id,
                    src.openaq_sensor_id,
                    src.location_id,
                    src.parameter_id,
                    src.unit,
                    CASE
                        WHEN existing_any.source_sensor_id IS NULL THEN COALESCE(src.first_seen_at, now())
                        ELSE now()
                    END,
                    NULL,
                    true,
                    src.row_hash
                FROM source_rows AS src
                LEFT JOIN dw.dim_sensor AS current_dim
                    ON current_dim.source_sensor_id = src.sensor_id
                   AND current_dim.is_current
                LEFT JOIN (
                    SELECT DISTINCT source_sensor_id
                    FROM dw.dim_sensor
                ) AS existing_any
                    ON existing_any.source_sensor_id = src.sensor_id
                WHERE current_dim.sensor_key IS NULL
                """
            )
            inserted = cur.rowcount
            return expired + inserted

    def load_measurement_facts(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dw.fact_air_quality_measurement (
                    source_measurement_id,
                    location_key,
                    sensor_key,
                    parameter_key,
                    date_key,
                    time_key,
                    risk_class_key,
                    measured_at,
                    measurement_value,
                    unit,
                    ingestion_run_id
                )
                SELECT
                    m.measurement_id,
                    dl.location_key,
                    ds.sensor_key,
                    dp.parameter_key,
                    to_char(m.measured_at AT TIME ZONE 'UTC', 'YYYYMMDD')::integer AS date_key,
                    (
                        EXTRACT(HOUR FROM m.measured_at AT TIME ZONE 'UTC')::integer * 100
                        + EXTRACT(MINUTE FROM m.measured_at AT TIME ZONE 'UTC')::integer
                    ) AS time_key,
                    rc.risk_class_key,
                    m.measured_at,
                    m.value,
                    m.unit,
                    m.ingestion_run_id
                FROM oltp.measurement_raw AS m
                JOIN oltp.sensor AS s
                    ON s.sensor_id = m.sensor_id
                JOIN dw.dim_sensor AS ds
                    ON ds.source_sensor_id = s.sensor_id
                   AND ds.is_current
                JOIN dw.dim_location AS dl
                    ON dl.source_location_id = s.location_id
                   AND dl.is_current
                JOIN dw.dim_parameter AS dp
                    ON dp.source_parameter_id = s.parameter_id
                LEFT JOIN dw.dim_risk_class AS rc
                    ON m.value >= rc.min_value
                   AND (rc.max_value IS NULL OR m.value < rc.max_value)
                WHERE m.value IS NOT NULL
                  AND m.value >= 0
                  AND m.value < 100000
                  AND NOT EXISTS (
                      SELECT 1
                      FROM dw.fact_air_quality_measurement AS existing
                      WHERE existing.source_measurement_id = m.measurement_id
                  )
                """
            )
            return cur.rowcount

    def load_alert_facts(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dw.fact_pollution_alert (
                    source_alert_id,
                    location_key,
                    parameter_key,
                    risk_class_key,
                    date_key,
                    time_key,
                    alert_level,
                    alert_status,
                    measurement_value,
                    generated_at
                )
                SELECT
                    pa.pollution_alert_id,
                    dl.location_key,
                    dp.parameter_key,
                    rc.risk_class_key,
                    to_char(pa.generated_at AT TIME ZONE 'UTC', 'YYYYMMDD')::integer AS date_key,
                    (
                        EXTRACT(HOUR FROM pa.generated_at AT TIME ZONE 'UTC')::integer * 100
                        + EXTRACT(MINUTE FROM pa.generated_at AT TIME ZONE 'UTC')::integer
                    ) AS time_key,
                    pa.alert_level,
                    pa.status,
                    m.value,
                    pa.generated_at
                FROM oltp.pollution_alert AS pa
                JOIN oltp.measurement_raw AS m
                    ON m.measurement_id = pa.measurement_id
                   AND m.measured_at = pa.measurement_measured_at
                JOIN oltp.sensor AS s
                    ON s.sensor_id = m.sensor_id
                JOIN dw.dim_location AS dl
                    ON dl.source_location_id = s.location_id
                   AND dl.is_current
                JOIN dw.dim_parameter AS dp
                    ON dp.source_parameter_id = s.parameter_id
                LEFT JOIN dw.dim_risk_class AS rc
                    ON rc.code = pa.alert_level
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM dw.fact_pollution_alert AS existing
                    WHERE existing.source_alert_id = pa.pollution_alert_id
                )
                """
            )
            return cur.rowcount


def run_etl(database_url: str) -> ETLResult:
    with psycopg.connect(database_url) as conn:
        repo = ETLRepository(conn)
        with conn.transaction():
            parameters = repo.sync_parameters()
            locations = repo.sync_locations()
            sensors = repo.sync_sensors()
            measurements = repo.load_measurement_facts()
            alerts = repo.load_alert_facts()

        return ETLResult(
            parameters=parameters,
            locations=locations,
            sensors=sensors,
            measurements=measurements,
            alerts=alerts,
        )


def main() -> int:
    try:
        result = run_etl(database_url_from_env())
    except Exception as exc:
        print(f"ETL failed: {exc}", file=sys.stderr)
        return 1

    print(
        "DW ETL completed: "
        f"parameters={result.parameters}, "
        f"locations={result.locations}, "
        f"sensors={result.sensors}, "
        f"measurements={result.measurements}, "
        f"alerts={result.alerts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
