from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import ModuleType

psycopg_stub = ModuleType("psycopg")
psycopg_stub.Connection = object
psycopg_stub.connect = None
sys.modules.setdefault("psycopg", psycopg_stub)

dotenv_stub = ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workers"))

import pandas as pd  # noqa: E402

from train_model import build_training_frame  # noqa: E402


class TrainModelFeatureTests(unittest.TestCase):
    def test_build_training_frame_creates_next_hour_target_features(self) -> None:
        frame = pd.DataFrame(
            {
                "sensor_key": [1, 1, 1, 1, 1, 1, 1],
                "location_key": [10, 10, 10, 10, 10, 10, 10],
                "parameter_key": [2, 2, 2, 2, 2, 2, 2],
                "measured_at": pd.date_range("2026-01-01", periods=7, freq="h", tz="UTC"),
                "measurement_value": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
                "weekday": [4] * 7,
                "is_weekend": [False] * 7,
                "hour": list(range(7)),
                "minute": [0] * 7,
            }
        )

        training_frame = build_training_frame(frame)

        self.assertEqual(len(training_frame), 1)
        row = training_frame.iloc[0]
        self.assertEqual(row["current_value"], 15.0)
        self.assertEqual(row["previous_value"], 14.0)
        self.assertEqual(row["rolling_3h"], 14.0)
        self.assertEqual(row["rolling_6h"], 12.5)
        self.assertEqual(row["target_value"], 16.0)


if __name__ == "__main__":
    unittest.main()
