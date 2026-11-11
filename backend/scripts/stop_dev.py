"""Stop development processes belonging to this checkout, never arbitrary port owners."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    if not shutil.which("lsof"):
        raise SystemExit("lsof is required to identify this project's development processes.")
    rows = subprocess.check_output(["ps", "-ax", "-o", "pid=,comm="], text=True).splitlines()
    own_ancestors = {os.getpid(), os.getppid()}
    targets = []
    for row in rows:
        pid_text, command = row.strip().split(None, 1)
        pid = int(pid_text)
        name = Path(command).name.lower()
        if pid in own_ancestors or not any(x in name for x in ("python", "node", "npm", "expo")):
            continue
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
        )
        paths = [Path(line[1:]) for line in result.stdout.splitlines() if line.startswith("n/")]
        if any(path == ROOT or ROOT in path.parents for path in paths):
            targets.append(pid)
    for pid in targets:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 10
    while targets and time.monotonic() < deadline:
        remaining = []
        for pid in targets:
            try:
                os.kill(pid, 0)
                remaining.append(pid)
            except ProcessLookupError:
                pass
        targets = remaining
        if targets:
            time.sleep(0.2)
    if targets:
        raise SystemExit("Some processes are still stopping. Retry make fclean shortly.")
    print("Project Python and Expo processes stopped.")
    if shutil.which("docker"):
        subprocess.run(
            ["docker", "compose", "--profile", "app", "--profile", "test", "stop"],
            cwd=ROOT / "backend",
            check=True,
        )
    print("Development services stopped; database volumes preserved.")


if __name__ == "__main__":
    main()
