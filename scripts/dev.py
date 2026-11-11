import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def interrupt(*_):
    raise KeyboardInterrupt


def main():
    processes = []
    signal.signal(signal.SIGTERM, interrupt)
    try:
        backend_env = {
            **os.environ,
            "CORS_ORIGINS": '["http://localhost:8081","http://127.0.0.1:8081"]',
        }
        processes.append(subprocess.Popen(
            ["sh", "start.sh", "--skip-install", "--host", "0.0.0.0", "--port", "8001"],
            cwd=ROOT / "backend", env=backend_env, start_new_session=True,
        ))
        processes.append(subprocess.Popen(
            ["npm", "run", "web", "--", "--port", "8081"],
            cwd=ROOT / "mobile", start_new_session=True,
            env={**os.environ, "EXPO_PUBLIC_API_URL": "http://localhost:8001",
                 "EXPO_PUBLIC_USE_MOCK": "false"},
        ))
        print("Frontend: http://localhost:8081 | API: http://localhost:8001/docs", flush=True)
        print("Press Ctrl+C to stop frontend, API, and email worker.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        return next((p.returncode for p in processes if p.returncode is not None), 1)
    except KeyboardInterrupt:
        return 0
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
