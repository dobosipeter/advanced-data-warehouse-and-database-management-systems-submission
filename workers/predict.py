from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb

from train_model import MODEL_ARTIFACT_PATH, MODEL_VERSION, ModelTrainingError


@dataclass(frozen=True)
class PredictionInput:
    location_key: int
    sensor_key: int
    parameter_key: int
    current_value: float
    previous_value: float
    rolling_3h: float
    rolling_6h: float
    hour: int
    minute: int
    weekday: int
    month: int
    target_measured_at: datetime


def database_url_from_env() -> str:
    load_dotenv()
    return os.getenv("DATABASE_URL", "postgresql://air_quality:change-me@db:5432/air_quality")


def load_model_artifact() -> dict[str, Any]:
    if not MODEL_ARTIFACT_PATH.exists():
        raise ModelTrainingError(f"Model artifact not found at {MODEL_ARTIFACT_PATH}.")
    return joblib.load(MODEL_ARTIFACT_PATH)


def load_prediction_inputs(database_url: str) -> list[PredictionInput]:
    query = """
        SELECT
            f.location_key,
            f.sensor_key,
            f.parameter_key,
            f.measured_at,
            f.measurement_value,
            dd.weekday,
            dt.hour,
            dt.minute
        FROM dw.fact_air_quality_measurement AS f
        JOIN dw.dim_parameter AS dp
            ON dp.parameter_key = f.parameter_key
        JOIN dw.dim_date AS dd
            ON dd.date_key = f.date_key
        JOIN dw.dim_time AS dt
            ON dt.time_key = f.time_key
        WHERE dp.code = 'pm25'
        ORDER BY f.sensor_key, f.measured_at
    """
    with psycopg.connect(database_url) as conn:
        frame = pd.read_sql(query, conn)

    if frame.empty:
        raise ModelTrainingError("No PM2.5 fact rows are available for prediction.")

    frame["measured_at"] = pd.to_datetime(frame["measured_at"], utc=True)
    grouped = frame.groupby("sensor_key")
    prediction_inputs: list[PredictionInput] = []
    for sensor_key, sensor_frame in grouped:
        sensor_frame = sensor_frame.sort_values("measured_at").reset_index(drop=True)
        if len(sensor_frame) < 6:
            continue
        latest = sensor_frame.iloc[-1]
        previous = sensor_frame.iloc[-2]
        rolling_3h = float(sensor_frame["measurement_value"].tail(3).mean())
        rolling_6h = float(sensor_frame["measurement_value"].tail(6).mean())
        target_measured_at = latest["measured_at"] + timedelta(hours=1)
        prediction_inputs.append(
            PredictionInput(
                location_key=int(latest["location_key"]),
                sensor_key=int(sensor_key),
                parameter_key=int(latest["parameter_key"]),
                current_value=float(latest["measurement_value"]),
                previous_value=float(previous["measurement_value"]),
                rolling_3h=rolling_3h,
                rolling_6h=rolling_6h,
                hour=int(latest["measured_at"].hour),
                minute=int(latest["measured_at"].minute),
                weekday=int(latest["weekday"]),
                month=int(latest["measured_at"].month),
                target_measured_at=target_measured_at.to_pydatetime().astimezone(UTC),
            )
        )

    if not prediction_inputs:
        raise ModelTrainingError("Need at least six historical PM2.5 rows per sensor to create predictions.")
    return prediction_inputs


def risk_class_key_for_value(conn: psycopg.Connection[Any], value: float) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT risk_class_key
            FROM dw.dim_risk_class
            WHERE %s >= min_value
              AND (max_value IS NULL OR %s < max_value)
            ORDER BY min_value DESC
            LIMIT 1
            """,
            (value, value),
        )
        row = cur.fetchone()
    return None if row is None else int(row[0])


def insert_predictions(
    database_url: str,
    model_artifact: dict[str, Any],
    prediction_inputs: list[PredictionInput],
) -> int:
    model = model_artifact["model"]
    model_name = str(model_artifact["model_name"])
    model_version = str(model_artifact.get("model_version", MODEL_VERSION))
    rows = [
        {
            "location_key": str(item.location_key),
            "sensor_key": str(item.sensor_key),
            "current_value": item.current_value,
            "previous_value": item.previous_value,
            "rolling_3h": item.rolling_3h,
            "rolling_6h": item.rolling_6h,
            "hour": item.hour,
            "minute": item.minute,
            "weekday": item.weekday,
            "month": item.month,
        }
        for item in prediction_inputs
    ]
    feature_frame = pd.DataFrame(rows)
    predictions = model.predict(feature_frame)

    inserted = 0
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            for item, predicted_value in zip(prediction_inputs, predictions, strict=True):
                predicted_value = float(predicted_value)
                date_key = int(item.target_measured_at.strftime("%Y%m%d"))
                time_key = item.target_measured_at.hour * 100 + item.target_measured_at.minute
                risk_class_key = risk_class_key_for_value(conn, predicted_value)
                feature_payload = Jsonb(
                    {
                        "current_value": item.current_value,
                        "previous_value": item.previous_value,
                        "rolling_3h": item.rolling_3h,
                        "rolling_6h": item.rolling_6h,
                        "hour": item.hour,
                        "minute": item.minute,
                        "weekday": item.weekday,
                        "month": item.month,
                    }
                )
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO dw.fact_prediction (
                            location_key,
                            sensor_key,
                            parameter_key,
                            target_date_key,
                            target_time_key,
                            target_measured_at,
                            predicted_value,
                            model_name,
                            model_version,
                            feature_payload,
                            risk_class_key
                        )
                        SELECT
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM dw.fact_prediction
                            WHERE location_key = %s
                              AND sensor_key = %s
                              AND parameter_key = %s
                              AND target_measured_at = %s
                              AND model_name = %s
                              AND model_version = %s
                        )
                        """,
                        (
                            item.location_key,
                            item.sensor_key,
                            item.parameter_key,
                            date_key,
                            time_key,
                            item.target_measured_at,
                            Decimal(f"{predicted_value:.4f}"),
                            model_name,
                            model_version,
                            feature_payload,
                            risk_class_key,
                            item.location_key,
                            item.sensor_key,
                            item.parameter_key,
                            item.target_measured_at,
                            model_name,
                            model_version,
                        ),
                    )
                    inserted += cur.rowcount
    return inserted


def generate_predictions(database_url: str) -> int:
    model_artifact = load_model_artifact()
    prediction_inputs = load_prediction_inputs(database_url)
    return insert_predictions(database_url, model_artifact, prediction_inputs)


def main() -> int:
    try:
        inserted = generate_predictions(database_url_from_env())
    except Exception as exc:
        print(f"Prediction generation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"status": "predicted", "inserted": inserted}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
