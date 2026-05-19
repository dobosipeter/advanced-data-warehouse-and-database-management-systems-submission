from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import psycopg
from dotenv import load_dotenv
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


MODEL_VERSION = "0.1.0"
MODEL_ARTIFACT_DIR = Path(__file__).resolve().parent / "model_artifacts"
MODEL_ARTIFACT_PATH = MODEL_ARTIFACT_DIR / "pm25_model.joblib"


class ModelTrainingError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelMetrics:
    model_name: str
    mae: float
    rmse: float
    r2: float
    train_rows: int
    test_rows: int


def database_url_from_env() -> str:
    load_dotenv()
    return os.getenv("DATABASE_URL", "postgresql://air_quality:change-me@db:5432/air_quality")


def load_pm25_measurements(database_url: str) -> pd.DataFrame:
    query = """
        SELECT
            f.sensor_key,
            f.location_key,
            f.parameter_key,
            f.measured_at,
            f.measurement_value,
            dd.weekday,
            dd.is_weekend,
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
        raise ModelTrainingError("No PM2.5 rows are available in dw.fact_air_quality_measurement.")

    frame["measured_at"] = pd.to_datetime(frame["measured_at"], utc=True)
    return frame


def build_training_frame(measurements: pd.DataFrame) -> pd.DataFrame:
    frame = measurements.copy()
    frame["location_key"] = frame["location_key"].astype(str)
    frame["sensor_key"] = frame["sensor_key"].astype(str)

    grouped = frame.groupby("sensor_key", group_keys=False)
    frame["current_value"] = frame["measurement_value"]
    frame["previous_value"] = grouped["measurement_value"].shift(1)
    frame["rolling_3h"] = grouped["measurement_value"].transform(lambda values: values.rolling(3, min_periods=3).mean())
    frame["rolling_6h"] = grouped["measurement_value"].transform(lambda values: values.rolling(6, min_periods=6).mean())
    frame["month"] = frame["measured_at"].dt.month
    frame["target_value"] = grouped["measurement_value"].shift(-1)
    frame["target_measured_at"] = grouped["measured_at"].shift(-1)

    frame = frame.dropna(
        subset=[
            "previous_value",
            "rolling_3h",
            "rolling_6h",
            "target_value",
            "target_measured_at",
        ]
    ).copy()
    if frame.empty:
        raise ModelTrainingError("Not enough PM2.5 history to build training features.")

    frame["target_measured_at"] = pd.to_datetime(frame["target_measured_at"], utc=True)
    return frame


def split_training_frame(training_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = training_frame.sort_values("target_measured_at").reset_index(drop=True)
    split_index = max(1, int(len(ordered) * 0.8))
    if split_index >= len(ordered):
        split_index = len(ordered) - 1
    if split_index <= 0:
        raise ModelTrainingError("Need at least two PM2.5 feature rows for train/test evaluation.")
    return ordered.iloc[:split_index].copy(), ordered.iloc[split_index:].copy()


def model_pipeline(model_name: str):
    categorical_features = ["location_key", "sensor_key"]
    numeric_features = [
        "current_value",
        "previous_value",
        "rolling_3h",
        "rolling_6h",
        "hour",
        "minute",
        "weekday",
        "month",
    ]
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_features),
            ("numeric", StandardScaler(), numeric_features),
        ]
    )
    estimator = (
        LinearRegression()
        if model_name == "linear-regression"
        else RandomForestRegressor(
            n_estimators=200,
            min_samples_leaf=2,
            random_state=42,
        )
    )
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", estimator),
        ]
    )


def evaluate_models(training_frame: pd.DataFrame) -> tuple[Pipeline, ModelMetrics]:
    train_frame, test_frame = split_training_frame(training_frame)
    feature_columns = [
        "location_key",
        "sensor_key",
        "current_value",
        "previous_value",
        "rolling_3h",
        "rolling_6h",
        "hour",
        "minute",
        "weekday",
        "month",
    ]
    X_train = train_frame[feature_columns]
    y_train = train_frame["target_value"]
    X_test = test_frame[feature_columns]
    y_test = test_frame["target_value"]

    best_pipeline: Pipeline | None = None
    best_metrics: ModelMetrics | None = None
    for model_name in ("linear-regression", "random-forest"):
        pipeline = model_pipeline(model_name)
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
        metrics = ModelMetrics(
            model_name=model_name,
            mae=float(mean_absolute_error(y_test, predictions)),
            rmse=float(math.sqrt(mean_squared_error(y_test, predictions))),
            r2=float(r2_score(y_test, predictions)),
            train_rows=len(train_frame),
            test_rows=len(test_frame),
        )
        if best_metrics is None or metrics.mae < best_metrics.mae:
            best_pipeline = pipeline
            best_metrics = metrics

    assert best_pipeline is not None and best_metrics is not None
    return best_pipeline, best_metrics


def persist_model(model: Pipeline, metrics: ModelMetrics, trained_at: datetime) -> Path:
    MODEL_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "metrics": asdict(metrics),
        "trained_at": trained_at.isoformat(),
        "model_name": metrics.model_name,
        "model_version": MODEL_VERSION,
    }
    joblib.dump(payload, MODEL_ARTIFACT_PATH)
    return MODEL_ARTIFACT_PATH


def train_model(database_url: str) -> tuple[ModelMetrics, Path]:
    measurements = load_pm25_measurements(database_url)
    training_frame = build_training_frame(measurements)
    model, metrics = evaluate_models(training_frame)
    artifact_path = persist_model(model, metrics, datetime.now(UTC))
    return metrics, artifact_path


def main() -> int:
    try:
        metrics, artifact_path = train_model(database_url_from_env())
    except Exception as exc:
        print(f"Model training failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "trained",
                "artifact_path": str(artifact_path),
                "model_name": metrics.model_name,
                "model_version": MODEL_VERSION,
                "mae": metrics.mae,
                "rmse": metrics.rmse,
                "r2": metrics.r2,
                "train_rows": metrics.train_rows,
                "test_rows": metrics.test_rows,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
