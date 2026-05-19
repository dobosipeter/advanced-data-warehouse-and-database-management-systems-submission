from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from fastapi.testclient import TestClient  # noqa: E402

from main import app, get_db_connection, settings  # noqa: E402


class FakeCursor:
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn
        self.last_query = ""

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, query: str, params=()) -> None:
        self.last_query = query
        self.conn.calls.append((query, params))

    def fetchone(self):
        if "current_database()" in self.last_query:
            return {"status": "ok", "database": "air_quality"}
        if "FROM upserted AS tr" in self.last_query or "FROM updated AS tr" in self.last_query:
            return {
                "threshold_rule_id": 8,
                "parameter_id": 2,
                "parameter_code": "pm25",
                "parameter_name": "PM2.5",
                "city": "Budapest",
                "warning_level": "high",
                "min_value": 25.0,
                "is_active": True,
                "updated_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
            }
        if "FROM updated AS a" in self.last_query:
            return {
                "pollution_alert_id": 4,
                "generated_at": datetime(2026, 5, 19, 0, 5, tzinfo=timezone.utc),
                "alert_level": "moderate",
                "status": "reviewed",
                "measurement_value": 12.3,
                "measurement_unit": "ug/m3",
                "measured_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
                "city": "Budapest",
                "location_name": "Budapest Downtown",
                "parameter_code": "pm25",
                "parameter_name": "PM2.5",
                "threshold_value": 10.0,
                "reviewed_at": datetime(2026, 5, 19, 1, 0, tzinfo=timezone.utc),
                "notes": "checked",
            }
        return None

    def fetchall(self):
        if "FROM oltp.location AS l" in self.last_query:
            return [
                {
                    "location_id": 1,
                    "openaq_location_id": 100,
                    "name": "Budapest Downtown",
                    "city": "Budapest",
                    "country": "HU",
                    "latitude": 47.4979,
                    "longitude": 19.0402,
                    "timezone": "Europe/Budapest",
                    "active_sensor_count": 2,
                    "latest_measurement_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
                }
            ]
        if "FROM oltp.measurement_raw AS m" in self.last_query:
            return [
                {
                    "measurement_id": 10,
                    "measured_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
                    "value": 12.3,
                    "unit": "ug/m3",
                    "city": "Budapest",
                    "location_name": "Budapest Downtown",
                    "parameter_code": "pm25",
                    "parameter_name": "PM2.5",
                    "sensor_id": 5,
                    "ingestion_run_id": 7,
                }
            ]
        if "FROM oltp.pollution_alert AS a" in self.last_query:
            return [
                {
                    "pollution_alert_id": 4,
                    "generated_at": datetime(2026, 5, 19, 0, 5, tzinfo=timezone.utc),
                    "alert_level": "moderate",
                    "status": "open",
                    "measurement_value": 12.3,
                    "measurement_unit": "ug/m3",
                    "measured_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
                    "city": "Budapest",
                    "location_name": "Budapest Downtown",
                    "parameter_code": "pm25",
                    "parameter_name": "PM2.5",
                    "threshold_value": 10.0,
                    "reviewed_at": None,
                    "notes": None,
                }
            ]
        if "FROM dw.fact_prediction AS fp" in self.last_query:
            return [
                {
                    "fact_prediction_id": 2,
                    "target_measured_at": datetime(2026, 5, 19, 1, 0, tzinfo=timezone.utc),
                    "predicted_value": 15.7,
                    "model_name": "random-forest",
                    "model_version": "0.1.0",
                    "city": "Budapest",
                    "location_name": "Budapest Downtown",
                    "parameter_code": "pm25",
                    "created_at": datetime(2026, 5, 19, 0, 30, tzinfo=timezone.utc),
                    "risk_class_label": "Moderate",
                    "actual_value": 14.9,
                    "absolute_error": 0.8,
                }
            ]
        if "FROM oltp.threshold_rule AS tr" in self.last_query:
            return [
                {
                    "threshold_rule_id": 8,
                    "parameter_id": 2,
                    "parameter_code": "pm25",
                    "parameter_name": "PM2.5",
                    "city": "Budapest",
                    "warning_level": "high",
                    "min_value": 25.0,
                    "is_active": True,
                    "updated_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
                }
            ]
        if "FROM oltp.ingestion_run_log" in self.last_query:
            return [
                {
                    "ingestion_run_id": 7,
                    "run_type": "incremental",
                    "status": "succeeded",
                    "started_at": datetime(2026, 5, 19, 0, 0, tzinfo=timezone.utc),
                    "finished_at": datetime(2026, 5, 19, 0, 1, tzinfo=timezone.utc),
                    "records_inserted": 23,
                    "records_failed": 0,
                    "error_message": None,
                }
            ]
        return []


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        return None


class APITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_conn = FakeConnection()
        app.dependency_overrides[get_db_connection] = lambda: self.fake_conn
        settings.demo_refresh_token = "secret"
        settings.demo_refresh_command = None
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health_returns_database_status(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "air_quality"})

    def test_locations_returns_rows(self) -> None:
        response = self.client.get("/locations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["city"], "Budapest")

    def test_measurements_support_filters(self) -> None:
        response = self.client.get("/measurements", params={"city": "Budapest", "parameter": "pm25"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["parameter_code"], "pm25")

    def test_alerts_support_status_filter(self) -> None:
        response = self.client.get("/alerts", params={"status": "open", "level": "moderate"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["alert_level"], "moderate")

    def test_predictions_return_rows(self) -> None:
        response = self.client.get("/predictions", params={"city": "Budapest", "location": "Budapest Downtown"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["model_name"], "random-forest")
        self.assertEqual(response.json()[0]["risk_class_label"], "Moderate")
        self.assertEqual(response.json()[0]["absolute_error"], 0.8)

    def test_thresholds_return_rows(self) -> None:
        response = self.client.get("/thresholds", params={"city": "Budapest"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["warning_level"], "high")

    def test_thresholds_can_be_upserted(self) -> None:
        response = self.client.post(
            "/thresholds",
            json={
                "parameter_code": "pm25",
                "city": "Budapest",
                "warning_level": "high",
                "min_value": 25,
                "is_active": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["threshold_rule_id"], 8)

    def test_alerts_can_be_reviewed(self) -> None:
        response = self.client.patch("/alerts/4", json={"status": "reviewed", "notes": "checked"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "reviewed")

    def test_ingestion_runs_return_rows(self) -> None:
        response = self.client.get("/ingestion-runs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["records_inserted"], 23)

    def test_demo_refresh_requires_configuration(self) -> None:
        response = self.client.post("/demo/refresh", headers={"X-Demo-Token": "secret"})

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
