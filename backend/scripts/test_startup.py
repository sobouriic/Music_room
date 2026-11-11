"""Credential-preservation regression tests; no database or Docker required."""

import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.dev import PLACEHOLDER, check_port, prepare_env


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / ".env.example").write_text(
            "JWT_SECRET=" + PLACEHOLDER + "\nMAIL_DIRECTORY=local\n"
        )

    def test_first_run_generates_private_configuration(self):
        prepare_env(self.root)
        target = self.root / ".env"
        content = target.read_text()
        self.assertNotIn(PLACEHOLDER, content)
        self.assertIn("MAIL_DIRECTORY=local", content)
        self.assertGreater(len(content.splitlines()[0].split("=", 1)[1]), 32)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_rerun_preserves_existing_credentials_exactly(self):
        content = 'JWT_SECRET="my-existing-secret-keep-it"\nGOOGLE_CLIENT_SECRET=keep-this-too\n'
        (self.root / ".env").write_text(content)
        prepare_env(self.root)
        self.assertEqual((self.root / ".env").read_text(), content)

    def test_example_key_is_replaced_without_changing_other_values(self):
        target = self.root / ".env"
        target.write_text("JWT_SECRET=" + PLACEHOLDER + "\nGOOGLE_CLIENT_SECRET=unchanged\n")
        prepare_env(self.root)
        self.assertNotIn(PLACEHOLDER, target.read_text())
        self.assertIn("GOOGLE_CLIENT_SECRET=unchanged\n", target.read_text())
        first = target.read_text()
        prepare_env(self.root)
        self.assertEqual(target.read_text(), first)

    def test_missing_key_is_added(self):
        target = self.root / ".env"
        target.write_text("GOOGLE_CLIENT_SECRET=unchanged")
        prepare_env(self.root)
        self.assertTrue(
            target.read_text().startswith("GOOGLE_CLIENT_SECRET=unchanged\nJWT_SECRET=")
        )

    def test_empty_quoted_key_is_generated(self):
        target = self.root / ".env"
        target.write_text('JWT_SECRET=""\n')
        prepare_env(self.root)
        self.assertGreater(len(target.read_text().split("=", 1)[1].strip()), 32)


class PortTests(unittest.TestCase):
    def test_active_listener_is_rejected(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, f"Port {port} is already in use"):
                check_port("127.0.0.1", port)

    def test_recently_closed_connection_allows_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port)) as client:
                connection, _ = listener.accept()
                connection.close()
                self.assertEqual(client.recv(1), b"")
        check_port("127.0.0.1", port)


class PathTests(unittest.TestCase):
    def test_launcher_from_unrelated_directory_with_spaces(self):
        import shutil

        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="music room startup ") as directory:
            root = Path(directory) / "project with spaces"
            (root / "scripts").mkdir(parents=True)
            for launcher, helper, option in [
                ("start.sh", "dev.py", "--setup-only"),
                ("test-api.sh", "check_api.py", "--skip-install"),
            ]:
                shutil.copy2(source / launcher, root / launcher)
                shutil.copy2(source / "scripts" / helper, root / "scripts" / helper)
                result = subprocess.run(
                    ["sh", str(root / launcher), "--help"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(option, result.stdout)


if __name__ == "__main__":
    unittest.main()
