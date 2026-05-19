from pathlib import Path
import unittest


class BackupScriptTests(unittest.TestCase):
    def test_backup_script_contains_required_operations(self) -> None:
        script = Path("scripts/backup_db.sh").read_text()

        required_fragments = [
            "pg_dump",
            "-Fc",
            "RETENTION_DAYS",
            "pg_restore",
            "vacuumdb",
            "REINDEX DATABASE",
            "dropdb",
            "createdb",
        ]

        for fragment in required_fragments:
            self.assertIn(fragment, script)

    def test_backup_cron_documents_daily_backup_and_weekly_maintenance(self) -> None:
        cron = Path("scripts/air_quality_backup.crontab").read_text()

        self.assertIn("./scripts/backup_db.sh backup", cron)
        self.assertIn("./scripts/backup_db.sh maintenance", cron)


if __name__ == "__main__":
    unittest.main()
