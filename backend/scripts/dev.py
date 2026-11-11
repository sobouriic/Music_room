"""One-command local setup and supervised API/email-worker startup on Linux."""

import argparse
import errno
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = "replace-with-at-least-32-random-characters"


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def prepare_env(root=ROOT):
    """Create missing configuration and replace only an unset/example JWT key."""
    import secrets

    target = root / ".env"
    if not target.exists():
        content = (root / ".env.example").read_text(encoding="utf-8")
        # Exclusive creation prevents a second invocation from overwriting a new .env.
        with open(
            target, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)
        ) as file:
            file.write(content.replace(PLACEHOLDER, secrets.token_urlsafe(48)))
        print("Created .env with a random JWT secret (development defaults).", flush=True)
        configure_compose_env(target)
        return

    # Preserve user configuration and any nonempty custom key, including quoted keys.
    lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
    found = False
    changed = False
    for index, line in enumerate(lines):
        key, separator, value = line.strip().partition("=")
        if separator and key.removeprefix("export ").strip() == "JWT_SECRET":
            found = True
            value = value.strip().strip("\"'")
            if value in ("", PLACEHOLDER):
                lines[index] = "JWT_SECRET=" + secrets.token_urlsafe(48) + "\n"
                changed = True
    if not found:
        lines.append("\nJWT_SECRET=" + secrets.token_urlsafe(48) + "\n")
        changed = True
    if changed:
        target.write_text("".join(lines), encoding="utf-8")
        print("Generated the missing/example JWT secret in .env.", flush=True)
    else:
        print("Using existing .env; credentials preserved.", flush=True)
    target.chmod(0o600)
    configure_compose_env(target)


def configure_compose_env(target):
    """Derive Compose credentials from the existing URL without changing DB passwords."""
    from urllib.parse import unquote, urlsplit, urlunsplit

    content = target.read_text(encoding="utf-8")
    values = {}
    for line in content.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip("\"'")
    parsed = urlsplit(values.get("DATABASE_URL", ""))
    if not parsed.username or not parsed.password or not parsed.path:
        return
    additions = {
        "POSTGRES_USER": unquote(parsed.username),
        "POSTGRES_PASSWORD": unquote(parsed.password),
        "POSTGRES_DB": parsed.path.lstrip("/"),
        "CONTAINER_DATABASE_URL": urlunsplit(
            (
                parsed.scheme,
                parsed.netloc.rsplit("@", 1)[0] + "@db:5432",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        ),
    }
    # Dotenv single quotes preserve dollar signs and other URI/password characters.
    for key, value in additions.items():
        if key not in values:
            if "'" in value or "\n" in value:
                raise SystemExit("Set Compose variables explicitly for this database credential")
            content += f"\n{key}='{value}'\n"
    target.write_text(content, encoding="utf-8")
    target.chmod(0o600)


def stop_process(process):
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def check_port(host, port):
    # Match Uvicorn: recently closed connections must not prevent a restart.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                raise RuntimeError(
                    f"Port {port} is already in use. Run "
                    f"'lsof -nP -iTCP:{port} -sTCP:LISTEN' to identify the server. "
                    "Stop that server before retrying make."
                ) from error
            raise RuntimeError(f"Cannot listen on {host}:{port}: {error.strerror}") from error


def serve(python, host, port, reload):
    # Fail before launching the mail worker if another server owns this port.
    check_port(host, port)
    command = [
        str(python),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
        "--no-access-log",
    ]
    if reload:
        command.append("--reload")
    processes = []
    try:
        processes.append(subprocess.Popen(command, cwd=ROOT, start_new_session=True))
        processes.append(
            subprocess.Popen(
                [str(python), "-m", "mandatory.services.email_service"],
                cwd=ROOT,
                start_new_session=True,
            )
        )
        address = "localhost" if host == "0.0.0.0" else host
        print(
            f"\nSwagger: http://{address}:{port}/docs\nAPI reload is enabled."
            if reload
            else f"\nSwagger: http://{address}:{port}/docs",
            flush=True,
        )
        print(
            "API and email worker started. Press Ctrl+C to stop both; PostgreSQL data is kept.",
            flush=True,
        )
        while all(process.poll() is None for process in processes):
            time.sleep(0.25)
        raise RuntimeError("API or email worker exited; see its output above.")
    finally:
        for process in reversed(processes):
            stop_process(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--setup-only", action="store_true", help="Install/configure/migrate, then exit"
    )
    parser.add_argument("--skip-install", action="store_true", help="Skip pip on subsequent starts")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Use 0.0.0.0 for physical-device testing"
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-reload", action="store_true", help="Disable API development auto-reload"
    )
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.exit(1, "Python 3.12 or newer is required.\n")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if shutil.which("docker") is None:
        parser.exit(
            1, "Install Docker Engine and the Compose plugin, then run this script again.\n"
        )
    try:
        run("docker", "info", "--format", "{{.ServerVersion}}")
        run("docker", "compose", "version")
        python = ROOT / ".venv" / "bin" / "python"
        if not python.exists():
            if args.skip_install:
                raise RuntimeError(
                    "No usable .venv exists. Run the launcher without --skip-install first."
                )
            print("Creating .venv...", flush=True)
            run(sys.executable, "-m", "venv", str(ROOT / ".venv"))
        run(
            str(python),
            "-c",
            "import sys; assert sys.version_info >= (3, 12), "
            "'The existing .venv needs Python 3.12 or newer'",
        )
        if not args.skip_install:
            print("Installing the tested dependencies...", flush=True)
            run(str(python), "-m", "pip", "install", "-r", "requirements.lock")
            run(str(python), "-m", "pip", "install", "--no-deps", "-e", ".")
        prepare_env()
        # Validate before starting/migrating anything; do not print settings or secrets.
        run(
            str(python),
            "-c",
            "from app.core.config import get_settings\n"
            "try:\n"
            "    settings = get_settings()\n"
            "except Exception:\n"
            "    raise SystemExit('Invalid configuration. Check .env against .env.example.')\n"
            "if settings.app_env != 'development':\n"
            "    raise SystemExit('This script requires APP_ENV=development.')\n",
        )
        run("docker", "compose", "up", "-d", "db", "--wait")
        run(str(python), "-m", "alembic", "upgrade", "head")
        if args.setup_only:
            print(
                "Setup complete. Run the same launcher with --skip-install to start the backend.",
                flush=True,
            )
        else:
            serve(python, args.host, args.port, not args.no_reload)
    except KeyboardInterrupt:
        print("\nBackend stopped. PostgreSQL remains available for your next start.", flush=True)
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        # Never echo subprocess arguments/configuration that might contain credentials.
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        else:
            print(
                "Startup failed. Check the command output above and ensure Docker is running.",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    raise SystemExit(main())
