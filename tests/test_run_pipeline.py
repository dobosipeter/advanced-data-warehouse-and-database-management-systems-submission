from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_pipeline.sh"


class RunPipelineScriptTestCase(unittest.TestCase):
    def make_fake_python(self, directory: Path, *, fail_stage: str | None = None) -> Path:
        command_log = directory / "command.log"
        script_path = directory / "fake-python"
        script_path.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s\\n' "$*" >> "{command_log}"
                if [[ -n "${{FAIL_STAGE:-}}" && "$*" == *"${{FAIL_STAGE}}"* ]]; then
                    exit 23
                fi
                exit 0
                """
            ),
            encoding="utf-8",
        )
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
        return script_path

    def run_pipeline(self, mode: str, *, fail_stage: str | None = None) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
        temp_dir = Path(tempfile.mkdtemp(prefix="run-pipeline-test-"))
        fake_python = self.make_fake_python(temp_dir, fail_stage=fail_stage)
        env = os.environ.copy()
        env["PYTHON_BIN"] = str(fake_python)
        env["PIPELINE_LOG_DIR"] = str(temp_dir / "logs")
        env["MODEL_ARTIFACT_PATH"] = str(temp_dir / "model_artifacts" / "pm25_model.joblib")
        if fail_stage is not None:
            env["FAIL_STAGE"] = fail_stage

        completed = subprocess.run(
            [str(SCRIPT_PATH), mode],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        command_log = temp_dir / "command.log"
        commands = command_log.read_text(encoding="utf-8").splitlines() if command_log.exists() else []
        return completed, commands, temp_dir

    def test_full_mode_runs_ingest_etl_and_predict_in_order(self) -> None:
        completed, commands, temp_dir = self.run_pipeline("full")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            commands,
            [
                "workers/ingest.py --incremental",
                "workers/etl.py",
                "workers/train_model.py",
                "workers/predict.py",
            ],
        )
        self.assertTrue((temp_dir / "logs" / "pipeline-latest.status").exists())

    def test_ingest_failure_stops_following_stages(self) -> None:
        completed, commands, _ = self.run_pipeline("full", fail_stage="workers/ingest.py")

        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(commands, ["workers/ingest.py --incremental"])
        self.assertIn("FAILED ingest", completed.stdout)

    def test_ingest_etl_mode_skips_prediction(self) -> None:
        completed, commands, _ = self.run_pipeline("ingest-etl")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(commands, ["workers/ingest.py --incremental", "workers/etl.py"])

    def test_train_predict_mode_runs_training_before_prediction(self) -> None:
        completed, commands, _ = self.run_pipeline("train-predict")

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(commands, ["workers/train_model.py", "workers/predict.py"])

    def test_predict_only_skips_training_when_model_artifact_exists(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="run-pipeline-test-"))
        fake_python = self.make_fake_python(temp_dir)
        artifact_path = temp_dir / "model_artifacts" / "pm25_model.joblib"
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_text("fake model", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHON_BIN"] = str(fake_python)
        env["PIPELINE_LOG_DIR"] = str(temp_dir / "logs")
        env["MODEL_ARTIFACT_PATH"] = str(artifact_path)

        completed = subprocess.run(
            [str(SCRIPT_PATH), "predict-only"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        commands = (temp_dir / "command.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(commands, ["workers/predict.py"])


if __name__ == "__main__":
    unittest.main()
