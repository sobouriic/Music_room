"""Run isolated endpoint/security/CORS tests without touching development accounts."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-install", action="store_true", help="Use existing test dependencies"
    )
    args = parser.parse_args()
    if not shutil.which("docker"):
        parser.exit(1, "Docker with Compose is required. Start Docker, then try again.\n")
    python = ROOT / ".venv/bin/python"
    reports = ROOT / ".test-results"
    try:
        run("docker", "info", "--format", "{{.ServerVersion}}")
        if not python.exists():
            if args.skip_install:
                parser.exit(1, "Run without --skip-install to create .venv.\n")
            run(sys.executable, "-m", "venv", str(ROOT / ".venv"))
        if not args.skip_install:
            run(str(python), "-m", "pip", "install", "-r", "requirements.lock")
            run(str(python), "-m", "pip", "install", "--no-deps", "-e", ".")
        # No .env creation or development database startup is needed for these tests.
        run("docker", "compose", "--profile", "test", "up", "-d", "test-db", "--wait")
        run(str(python), "-m", "unittest", "scripts.test_startup")
        reports.mkdir(exist_ok=True)
        coverage = reports / "api-coverage.json"
        coverage.unlink(missing_ok=True)
        print("\nTesting every API operation, CORS, privacy, tokens and concurrency...", flush=True)
        result = subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "tests",
                "-v",
                "--tb=short",
                "--check-api-coverage",
                "--api-coverage-report",
                str(coverage),
                "--junitxml",
                str(reports / "api-tests.xml"),
            ],
            cwd=ROOT,
            env={
                **os.environ,
                "TEST_DATABASE_URL": "postgresql+psycopg://music:music_test_only@localhost:5433/music_room_test",
            },
        )
        if coverage.exists():
            report = json.loads(coverage.read_text())
            print(f"\nAPI operations exercised: {len(report['tested'])}/{len(report['required'])}")
            for operation in report["required"]:
                print(("TESTED  " if operation in report["tested"] else "MISSING  ") + operation)
        print(f"\nReports: {reports}")
        print(
            "Google calls were mocked; mail was written to local test files. "
            "Live Google and mobile integration need separate tests."
        )
        return result.returncode
    except (OSError, subprocess.CalledProcessError):
        print("Test setup failed. Check the output above and Docker access.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
