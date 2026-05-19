from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

psycopg_stub = ModuleType("psycopg")
psycopg_stub.Connection = object
psycopg_stub.connect = None
sys.modules.setdefault("psycopg", psycopg_stub)

psycopg_types_stub = ModuleType("psycopg.types")
sys.modules.setdefault("psycopg.types", psycopg_types_stub)

psycopg_types_json_stub = ModuleType("psycopg.types.json")
psycopg_types_json_stub.Jsonb = lambda value: value
sys.modules.setdefault("psycopg.types.json", psycopg_types_json_stub)

requests_stub = ModuleType("requests")
requests_stub.RequestException = Exception
requests_stub.Session = object
sys.modules.setdefault("requests", requests_stub)

dotenv_stub = ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workers"))

from ingest import IngestionConfig, IngestionError, run_ingestion  # noqa: E402


class FakeTransaction:
    def __enter__(self) -> "FakeTransaction":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


class FakeOpenAQClient:
    def __init__(self, config: IngestionConfig) -> None:
        self.config = config

    def locations(self):
        yield (
            {"page": 1},
            {
                "results": [
                    {
                        "id": 1,
                        "name": "Station 1",
                        "city": "Budapest",
                        "country": {"code": "HU"},
                        "coordinates": {"latitude": 47.5, "longitude": 19.0},
                        "timezone": "Europe/Budapest",
                        "sensors": [
                            {"id": 1, "parameter": {"name": "pm25", "units": "ug/m3"}},
                            {"id": 2, "parameter": {"name": "pm25", "units": "ug/m3"}},
                        ],
                    }
                ]
            },
        )

    def sensors(self, openaq_location_id: int):
        return iter(())

    def measurements(self, openaq_sensor_id: int, datetime_from, datetime_to):
        yield (
            {"page": 1},
            {
                "results": [
                    {
                        "value": 30 if openaq_sensor_id == 1 else 12,
                        "unit": "ug/m3",
                        "datetime": {"utc": f"2026-05-19T00:00:0{openaq_sensor_id}Z"},
                        "parameter": {"units": "ug/m3"},
                    }
                ]
            },
        )


class FailingLocationsClient(FakeOpenAQClient):
    def locations(self):
        raise IngestionError("locations endpoint failed")


class FakeRepository:
    instances: list["FakeRepository"] = []

    def __init__(self, conn: FakeConnection) -> None:
        self.conn = conn
        self.finished_runs: list[tuple[str, int, int, str | None]] = []
        FakeRepository.instances.append(self)

    def create_run(self, run_type: str) -> int:
        return 1

    def finish_run(self, run_id: int, status: str, inserted: int, failed: int, error: str | None = None) -> None:
        self.finished_runs.append((status, inserted, failed, error))

    def last_successful_watermark(self):
        return None

    def store_raw_response(self, run_id: int, endpoint: str, request_url: str, params: dict, payload: dict) -> None:
        return None

    def upsert_location(self, location: dict) -> int:
        return int(location["id"])

    def upsert_sensor(self, sensor: dict, location_id: int) -> int:
        return int(sensor["id"])

    def ensure_default_pm25_threshold_rules(self, city: str) -> None:
        return None

    def insert_measurement(self, sensor_id: int, run_id: int, measurement: dict) -> int | None:
        if measurement.get("value") is None:
            raise IngestionError("Measurement payload missing datetime/value")
        if sensor_id == 2:
            raise RuntimeError("bad sensor batch")
        return 1000 + sensor_id


class RunIngestionTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeRepository.instances.clear()
        self.config = IngestionConfig(
            database_url="postgresql://example",
            openaq_api_key="test-key",
            openaq_base_url="https://api.openaq.org/v3",
            bbox="18.9,47.3,19.3,47.6",
            iso="HU",
            cities=("Budapest",),
            parameters=("pm25",),
            history_days=30,
            page_limit=100,
            max_pages=2,
            max_locations=None,
            max_sensors=None,
            request_timeout=30,
            retry_count=1,
            retry_backoff_seconds=0.1,
        )

    def test_run_ingestion_marks_partial_when_sensor_batch_rolls_back(self) -> None:
        with (
            patch("ingest.psycopg.connect", return_value=FakeConnection()),
            patch("ingest.OpenAQClient", FakeOpenAQClient),
            patch("ingest.IngestionRepository", FakeRepository),
        ):
            inserted, failed = run_ingestion(self.config, "initial")

        self.assertEqual((inserted, failed), (1, 1))
        repo = FakeRepository.instances[0]
        self.assertEqual(repo.finished_runs[-1][0], "partial")
        self.assertIn("sensor 2 at location 1 rolled back", repo.finished_runs[-1][3] or "")

    def test_run_ingestion_skips_invalid_measurements_without_rolling_back_sensor(self) -> None:
        class InvalidMeasurementClient(FakeOpenAQClient):
            def locations(self):
                yield (
                    {"page": 1},
                    {
                        "results": [
                            {
                                "id": 1,
                                "name": "Station 1",
                                "city": "Budapest",
                                "country": {"code": "HU"},
                                "coordinates": {"latitude": 47.5, "longitude": 19.0},
                                "timezone": "Europe/Budapest",
                                "sensors": [
                                    {"id": 1, "parameter": {"name": "pm25", "units": "ug/m3"}},
                                ],
                            }
                        ]
                    },
                )

            def measurements(self, openaq_sensor_id: int, datetime_from, datetime_to):
                yield (
                    {"page": 1},
                    {
                        "results": [
                            {
                                "value": None,
                                "unit": "ug/m3",
                                "datetime": {"utc": "2026-05-19T00:00:00Z"},
                                "parameter": {"name": "pm25", "units": "ug/m3"},
                            },
                            {
                                "value": 18,
                                "unit": "ug/m3",
                                "datetime": {"utc": "2026-05-19T01:00:00Z"},
                                "parameter": {"name": "pm25", "units": "ug/m3"},
                            },
                        ]
                    },
                )

        with (
            patch("ingest.psycopg.connect", return_value=FakeConnection()),
            patch("ingest.OpenAQClient", InvalidMeasurementClient),
            patch("ingest.IngestionRepository", FakeRepository),
        ):
            inserted, failed = run_ingestion(self.config, "initial")

        self.assertEqual((inserted, failed), (1, 1))
        repo = FakeRepository.instances[0]
        self.assertEqual(repo.finished_runs[-1][0], "partial")
        self.assertIn("measurement skipped", repo.finished_runs[-1][3] or "")

    def test_run_ingestion_marks_failed_for_run_level_error(self) -> None:
        with (
            patch("ingest.psycopg.connect", return_value=FakeConnection()),
            patch("ingest.OpenAQClient", FailingLocationsClient),
            patch("ingest.IngestionRepository", FakeRepository),
        ):
            with self.assertRaises(IngestionError):
                run_ingestion(self.config, "initial")

        repo = FakeRepository.instances[0]
        self.assertEqual(repo.finished_runs[-1][0], "failed")
        self.assertIn("run failed: locations endpoint failed", repo.finished_runs[-1][3] or "")


if __name__ == "__main__":
    unittest.main()
