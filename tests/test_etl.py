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

dotenv_stub = ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: None
sys.modules.setdefault("dotenv", dotenv_stub)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workers"))

from etl import ETLResult, database_url_from_env  # noqa: E402


class ETLConfigTests(unittest.TestCase):
    def test_database_url_defaults_to_compose_database(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                database_url_from_env(),
                "postgresql://air_quality:change-me@db:5432/air_quality",
            )

    def test_etl_result_is_printable_summary_data(self) -> None:
        result = ETLResult(parameters=1, locations=2, sensors=3, measurements=4, alerts=5)

        self.assertEqual(result.measurements, 4)

    def test_etl_worker_contains_scd2_expiration_logic(self) -> None:
        etl_source = Path("workers/etl.py").read_text()

        self.assertIn("valid_to = now()", etl_source)
        self.assertIn("is_current = false", etl_source)
        self.assertIn("row_hash <>", etl_source)


if __name__ == "__main__":
    unittest.main()
