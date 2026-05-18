from pathlib import Path


def test_expected_project_directories_exist() -> None:
    expected = [
        "frontend",
        "api",
        "workers",
        "database/init",
        "reverse-proxy",
        "scripts",
        "reports/dbms",
        "reports/dw",
        "slides/dbms",
        "slides/dw",
        "diagrams",
        "tests",
    ]

    for directory in expected:
        assert Path(directory).is_dir()
