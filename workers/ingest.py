from __future__ import annotations

import argparse
import os
import sys
import time
from decimal import Decimal
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


DEFAULT_BUDAPEST_BBOX = "18.9250,47.3494,19.3340,47.6130"
DEFAULT_PARAMETERS = "pm25,pm10,no2,o3"
MAX_ERROR_MESSAGE_LENGTH = 4000
MEASUREMENT_PAGE_LIMIT = 250
DEFAULT_PM25_THRESHOLD_RULES = (
    ("low", Decimal("0")),
    ("moderate", Decimal("10")),
    ("high", Decimal("25")),
    ("critical", Decimal("50")),
)


class IngestionError(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionConfig:
    database_url: str
    openaq_api_key: str
    openaq_base_url: str
    bbox: str
    iso: str
    cities: tuple[str, ...]
    parameters: tuple[str, ...]
    history_days: int
    incremental_overlap_hours: int
    page_limit: int
    max_pages: int
    max_locations: int | None
    max_sensors: int | None
    request_timeout: int
    retry_count: int
    retry_backoff_seconds: float

    @classmethod
    def from_env(cls, args: argparse.Namespace) -> IngestionConfig:
        load_dotenv()

        database_url = os.getenv("DATABASE_URL", "postgresql://air_quality:change-me@db:5432/air_quality")
        api_key = os.getenv("OPENAQ_API_KEY", "").strip()
        if not api_key:
            raise IngestionError("OPENAQ_API_KEY is required for OpenAQ API v3 requests.")

        return cls(
            database_url=database_url,
            openaq_api_key=api_key,
            openaq_base_url=os.getenv("OPENAQ_BASE_URL", "https://api.openaq.org/v3").rstrip("/"),
            bbox=args.bbox or os.getenv("OPENAQ_BBOX", DEFAULT_BUDAPEST_BBOX),
            iso=args.iso or os.getenv("OPENAQ_ISO", "HU"),
            cities=csv_tuple(args.cities or os.getenv("OPENAQ_CITIES", "Budapest")),
            parameters=csv_tuple(args.parameters or os.getenv("OPENAQ_PARAMETERS", DEFAULT_PARAMETERS)),
            history_days=args.history_days or int(os.getenv("INGESTION_HISTORY_DAYS", "180")),
            incremental_overlap_hours=args.incremental_overlap_hours
            or int(os.getenv("INGESTION_INCREMENTAL_OVERLAP_HOURS", "12")),
            page_limit=args.page_limit or int(os.getenv("OPENAQ_PAGE_LIMIT", "1000")),
            max_pages=args.max_pages or int(os.getenv("OPENAQ_MAX_PAGES", "20")),
            max_locations=args.max_locations if args.max_locations is not None else env_int("OPENAQ_MAX_LOCATIONS", 10),
            max_sensors=args.max_sensors if args.max_sensors is not None else env_int("OPENAQ_MAX_SENSORS", None),
            request_timeout=int(os.getenv("OPENAQ_REQUEST_TIMEOUT_SECONDS", "30")),
            retry_count=int(os.getenv("OPENAQ_RETRY_COUNT", "3")),
            retry_backoff_seconds=float(os.getenv("OPENAQ_RETRY_BACKOFF_SECONDS", "1.5")),
        )


def csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def env_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


class OpenAQClient:
    def __init__(self, config: IngestionConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"X-API-Key": config.openaq_api_key})

    def get_page(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.openaq_base_url}{endpoint}"
        last_error: Exception | None = None

        for attempt in range(1, self.config.retry_count + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.config.request_timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    raise IngestionError(f"OpenAQ returned retryable HTTP {response.status_code}: {response.text[:300]}")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError, IngestionError) as exc:
                last_error = exc
                if attempt == self.config.retry_count:
                    break
                time.sleep(self.config.retry_backoff_seconds * attempt)

        raise IngestionError(f"OpenAQ request failed for {endpoint}: {last_error}") from last_error

    def iter_pages(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        page_limit: int | None = None,
    ) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
        effective_page_limit = page_limit or self.config.page_limit
        for page in range(1, self.config.max_pages + 1):
            page_params = {"limit": effective_page_limit, "page": page, **params}
            payload = self.get_page(endpoint, page_params)
            yield page_params, payload

            results = payload.get("results") or []
            if len(results) < effective_page_limit:
                break

    def locations(self) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
        params: dict[str, Any] = {
            "bbox": self.config.bbox,
            "iso": self.config.iso,
            "parameters_id": ",".join(parameter_id_for_code(code) for code in self.config.parameters),
        }
        yield from self.iter_pages("/locations", params)

    def sensors(self, openaq_location_id: int) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
        yield from self.iter_pages(f"/locations/{openaq_location_id}/sensors", {})

    def measurements(
        self,
        openaq_sensor_id: int,
        datetime_from: datetime,
        datetime_to: datetime,
    ) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
        params = {
            "datetime_from": datetime_from.isoformat().replace("+00:00", "Z"),
            "datetime_to": datetime_to.isoformat().replace("+00:00", "Z"),
        }
        yield from self.iter_pages(
            f"/sensors/{openaq_sensor_id}/measurements",
            params,
            page_limit=min(self.config.page_limit, MEASUREMENT_PAGE_LIMIT),
        )


def parameter_id_for_code(code: str) -> str:
    known = {"pm10": "1", "pm25": "2", "no2": "7", "o3": "10"}
    return known.get(code.lower(), code)


class IngestionRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self.conn = conn

    def create_run(self, run_type: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO oltp.ingestion_run_log (run_type, status)
                VALUES (%s, 'running')
                RETURNING ingestion_run_id
                """,
                (run_type,),
            )
            return int(cur.fetchone()[0])

    def finish_run(self, run_id: int, status: str, inserted: int, failed: int, error: str | None = None) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE oltp.ingestion_run_log
                SET finished_at = now(),
                    status = %s,
                    records_inserted = %s,
                    records_failed = %s,
                    error_message = %s
                WHERE ingestion_run_id = %s
                """,
                (status, inserted, failed, error, run_id),
            )

    def latest_measurement_watermark(self) -> datetime | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT max(measured_at) FROM oltp.measurement_raw")
            value = cur.fetchone()[0]
            return value

    def last_successful_run_watermark(self) -> datetime | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(COALESCE(finished_at, started_at))
                FROM oltp.ingestion_run_log
                WHERE status = 'succeeded'
                """
            )
            value = cur.fetchone()[0]
            return value

    def store_raw_response(
        self,
        run_id: int,
        endpoint: str,
        request_url: str,
        params: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO staging.raw_api_response
                    (ingestion_run_id, source_endpoint, request_url, request_params, response_body)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_id, endpoint, request_url, Jsonb(params), Jsonb(payload)),
            )

    def upsert_parameter(self, parameter: dict[str, Any]) -> int:
        code = (parameter.get("name") or parameter.get("code") or "").lower()
        if not code:
            raise IngestionError(f"Parameter payload has no name/code: {parameter}")

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO oltp.parameter
                    (openaq_parameter_id, code, display_name, preferred_unit, description)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (code) DO UPDATE
                SET openaq_parameter_id = EXCLUDED.openaq_parameter_id,
                    display_name = EXCLUDED.display_name,
                    preferred_unit = EXCLUDED.preferred_unit,
                    updated_at = now(),
                    is_active = true
                RETURNING parameter_id
                """,
                (
                    parameter.get("id"),
                    code,
                    parameter.get("displayName") or code.upper(),
                    normalize_unit(parameter.get("units") or parameter.get("unit") or "unknown"),
                    parameter.get("description"),
                ),
            )
            return int(cur.fetchone()[0])

    def upsert_location(self, location: dict[str, Any]) -> int:
        country = location.get("country") or {}
        coordinates = location.get("coordinates") or {}
        city = location_city_name(location)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO oltp.location
                    (openaq_location_id, name, city, country, latitude, longitude, timezone, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (openaq_location_id) DO UPDATE
                SET name = EXCLUDED.name,
                    city = EXCLUDED.city,
                    country = EXCLUDED.country,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    timezone = EXCLUDED.timezone,
                    raw_payload = EXCLUDED.raw_payload,
                    last_seen_at = now(),
                    is_active = true
                RETURNING location_id
                """,
                (
                    location["id"],
                    location.get("name") or f"OpenAQ location {location['id']}",
                    city,
                    country.get("code") or country.get("name") or "Unknown",
                    coordinates.get("latitude"),
                    coordinates.get("longitude"),
                    location.get("timezone"),
                    Jsonb(location),
                ),
            )
            return int(cur.fetchone()[0])

    def upsert_sensor(self, sensor: dict[str, Any], location_id: int) -> int:
        parameter_id = self.upsert_parameter(sensor["parameter"])

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO oltp.sensor
                    (openaq_sensor_id, location_id, parameter_id, unit, raw_payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (openaq_sensor_id) DO UPDATE
                SET location_id = EXCLUDED.location_id,
                    parameter_id = EXCLUDED.parameter_id,
                    unit = EXCLUDED.unit,
                    raw_payload = EXCLUDED.raw_payload,
                    last_seen_at = now(),
                    is_active = true
                RETURNING sensor_id
                """,
                (
                    sensor["id"],
                    location_id,
                    parameter_id,
                    normalize_unit(sensor.get("parameter", {}).get("units") or sensor.get("unit") or "unknown"),
                    Jsonb(sensor),
                ),
            )
            return int(cur.fetchone()[0])

    def ensure_default_pm25_threshold_rules(self, city: str) -> None:
        with self.conn.cursor() as cur:
            for warning_level, min_value in DEFAULT_PM25_THRESHOLD_RULES:
                cur.execute(
                    """
                    INSERT INTO oltp.threshold_rule (parameter_id, city, warning_level, min_value)
                    SELECT parameter_id, %s, %s, %s
                    FROM oltp.parameter
                    WHERE code = 'pm25'
                    ON CONFLICT (parameter_id, city, warning_level) DO NOTHING
                    """,
                    (city, warning_level, min_value),
                )

    def insert_measurement(self, sensor_id: int, run_id: int, measurement: dict[str, Any]) -> int | None:
        measured_at = measurement_time(measurement)
        value = measurement.get("value")
        parameter = measurement.get("parameter") or {}
        unit = normalize_unit(parameter.get("units") or measurement.get("unit") or "unknown")
        if measured_at is None or value is None:
            raise IngestionError(f"Measurement payload missing datetime/value: {measurement}")

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO oltp.measurement_raw
                    (sensor_id, measured_at, value, unit, ingestion_run_id, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (sensor_id, measured_at) DO NOTHING
                RETURNING measurement_id
                """,
                (sensor_id, measured_at, value, unit, run_id, Jsonb(measurement)),
            )
            row = cur.fetchone()
            return None if row is None else int(row[0])

def normalize_unit(unit: str) -> str:
    return unit.replace("µ", "u").replace("³", "3")


def location_city_name(location: dict[str, Any]) -> str:
    return location.get("locality") or location.get("city") or location.get("name") or "Unknown"


def measurement_time(measurement: dict[str, Any]) -> str | None:
    datetime_payload = measurement.get("datetime") or {}
    if datetime_payload.get("utc"):
        return datetime_payload["utc"]

    period = measurement.get("period") or {}
    datetime_from = period.get("datetimeFrom") or {}
    if datetime_from.get("utc"):
        return datetime_from["utc"]

    return measurement.get("date") or measurement.get("datetimeUtc")


def location_matches_scope(location: dict[str, Any], cities: tuple[str, ...]) -> bool:
    if not cities:
        return True
    candidates = [
        location.get("locality"),
        location.get("city"),
        location.get("name"),
    ]
    haystack = " ".join(str(value).lower() for value in candidates if value)
    return any(city.lower() in haystack for city in cities)


def sensor_matches_scope(sensor: dict[str, Any], parameters: tuple[str, ...]) -> bool:
    parameter = sensor.get("parameter") or {}
    return (parameter.get("name") or "").lower() in {item.lower() for item in parameters}


def summarize_measurement_error(sensor_id: int, measurement: dict[str, Any], exc: Exception) -> str:
    measured_at = measurement_time(measurement) or "unknown"
    parameter_name = (measurement.get("parameter") or {}).get("name") or "unknown"
    value = measurement.get("value")
    return (
        f"sensor {sensor_id} measurement skipped at {measured_at} "
        f"for parameter {parameter_name} with value {value}: {exc}"
    )


def summarize_errors(errors: list[str]) -> str | None:
    if not errors:
        return None
    summary = " | ".join(errors)
    if len(summary) <= MAX_ERROR_MESSAGE_LENGTH:
        return summary
    return f"{summary[: MAX_ERROR_MESSAGE_LENGTH - 3]}..."


def run_ingestion(config: IngestionConfig, mode: str) -> tuple[int, int]:
    client = OpenAQClient(config)
    inserted = 0
    failed = 0
    error_messages: list[str] = []

    with psycopg.connect(config.database_url, autocommit=True) as conn:
        repo = IngestionRepository(conn)
        with conn.transaction():
            run_id = repo.create_run(mode)

        try:
            now = datetime.now(UTC)
            if mode == "incremental":
                latest_measurement = repo.latest_measurement_watermark()
                if latest_measurement is not None:
                    datetime_from = latest_measurement - timedelta(hours=config.incremental_overlap_hours)
                else:
                    datetime_from = repo.last_successful_run_watermark() or now - timedelta(days=1)
            else:
                datetime_from = now - timedelta(days=config.history_days)

            seen_locations = 0
            seen_sensors = 0

            for params, payload in client.locations():
                with conn.transaction():
                    repo.store_raw_response(
                        run_id,
                        "/locations",
                        f"{config.openaq_base_url}/locations",
                        params,
                        payload,
                    )

                for location in payload.get("results") or []:
                    if not location_matches_scope(location, config.cities):
                        continue
                    if config.max_locations is not None and seen_locations >= config.max_locations:
                        break

                    try:
                        with conn.transaction():
                            seen_locations += 1
                            location_id = repo.upsert_location(location)
                            if "pm25" in {parameter.lower() for parameter in config.parameters}:
                                repo.ensure_default_pm25_threshold_rules(location_city_name(location))
                            sensors = [
                                sensor
                                for sensor in location.get("sensors", [])
                                if sensor_matches_scope(sensor, config.parameters)
                            ]

                            if not sensors:
                                for sensor_params, sensor_payload in client.sensors(location["id"]):
                                    repo.store_raw_response(
                                        run_id,
                                        f"/locations/{location['id']}/sensors",
                                        f"{config.openaq_base_url}/locations/{location['id']}/sensors",
                                        sensor_params,
                                        sensor_payload,
                                    )
                                    sensors.extend(
                                        sensor
                                        for sensor in sensor_payload.get("results") or []
                                        if sensor_matches_scope(sensor, config.parameters)
                                    )

                            for sensor in sensors:
                                if config.max_sensors is not None and seen_sensors >= config.max_sensors:
                                    break

                                seen_sensors += 1
                                try:
                                    with conn.transaction():
                                        sensor_id = repo.upsert_sensor(sensor, location_id)
                                        for measurement_params, measurement_payload in client.measurements(
                                            sensor["id"],
                                            datetime_from,
                                            now,
                                        ):
                                            repo.store_raw_response(
                                                run_id,
                                                f"/sensors/{sensor['id']}/measurements",
                                                f"{config.openaq_base_url}/sensors/{sensor['id']}/measurements",
                                                measurement_params,
                                                measurement_payload,
                                            )
                                            for measurement in measurement_payload.get("results") or []:
                                                try:
                                                    measurement_id = repo.insert_measurement(
                                                        sensor_id,
                                                        run_id,
                                                        measurement,
                                                    )
                                                except IngestionError as exc:
                                                    failed += 1
                                                    error_messages.append(
                                                        summarize_measurement_error(sensor["id"], measurement, exc)
                                                    )
                                                    continue

                                                if measurement_id is not None:
                                                    inserted += 1
                                except Exception as exc:
                                    failed += 1
                                    error_messages.append(
                                        f"sensor {sensor['id']} at location {location['id']} rolled back: {exc}"
                                    )
                    except Exception as exc:
                        failed += 1
                        error_messages.append(f"location {location['id']} rolled back: {exc}")

                    if config.max_sensors is not None and seen_sensors >= config.max_sensors:
                        break

                if config.max_locations is not None and seen_locations >= config.max_locations:
                    break

            final_status = "partial" if failed else "succeeded"
            with conn.transaction():
                repo.finish_run(run_id, final_status, inserted, failed, summarize_errors(error_messages))
            return inserted, failed
        except Exception as exc:
            error_messages.append(f"run failed: {exc}")
            with conn.transaction():
                repo.finish_run(run_id, "failed", inserted, failed + 1, summarize_errors(error_messages))
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest OpenAQ data into staging and OLTP tables.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initial", action="store_true", help="Run the initial historical load.")
    mode.add_argument("--incremental", action="store_true", help="Run an incremental load.")
    parser.add_argument("--bbox", help="WGS84 bounding box: min_lon,min_lat,max_lon,max_lat.")
    parser.add_argument("--iso", help="ISO 3166-1 alpha-2 country code.")
    parser.add_argument("--cities", help="Comma-separated locality/name filters.")
    parser.add_argument("--parameters", help="Comma-separated OpenAQ parameter names, e.g. pm25,pm10,no2,o3.")
    parser.add_argument("--history-days", type=int, help="Historical window for initial loads.")
    parser.add_argument(
        "--incremental-overlap-hours",
        type=int,
        help="Hours to subtract from the latest ingested measurement timestamp during incremental loads.",
    )
    parser.add_argument("--page-limit", type=int, help="OpenAQ page size.")
    parser.add_argument("--max-pages", type=int, help="Maximum pages to request per endpoint.")
    parser.add_argument("--max-locations", type=int, help="Maximum matching locations to ingest.")
    parser.add_argument("--max-sensors", type=int, help="Maximum matching sensors to ingest.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    mode = "initial" if args.initial else "incremental"

    try:
        config = IngestionConfig.from_env(args)
        inserted, failed = run_ingestion(config, mode)
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"OpenAQ {mode} ingestion completed: inserted={inserted}, failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
