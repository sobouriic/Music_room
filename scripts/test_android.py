"""Android command checks without starting emulators or contacting ADB."""

import subprocess
import unittest
from unittest.mock import MagicMock, mock_open, patch

from scripts.android import choose_device, prepare


class AndroidSetupTests(unittest.TestCase):
    def test_no_device_can_be_started(self):
        self.assertIsNone(choose_device([]))

    def test_multiple_devices_require_explicit_selection(self):
        rows = [("emulator-5554", "device"), ("phone", "device")]
        with self.assertRaisesRegex(RuntimeError, "ANDROID_SERIAL"):
            choose_device(rows)
        self.assertEqual(choose_device(rows, "phone"), "phone")

    def test_unauthorized_device_has_useful_message(self):
        with self.assertRaisesRegex(RuntimeError, "authorize"):
            choose_device([("phone", "unauthorized")])

    @patch("scripts.android.subprocess.run")
    def test_connected_device_forwards_both_ports(self, run):
        run.side_effect = [
            subprocess.CompletedProcess(
                [], 0, "List of devices attached\nphone\tdevice\n"
            ),
            subprocess.CompletedProcess([], 0, "1\n"),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
        ]
        prepare("/sdk/platform-tools/adb", "/sdk/emulator/emulator", 8083)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(
            [
                "/sdk/platform-tools/adb",
                "-s",
                "phone",
                "reverse",
                "tcp:8083",
                "tcp:8083",
            ],
            commands,
        )
        self.assertIn(
            [
                "/sdk/platform-tools/adb",
                "-s",
                "phone",
                "reverse",
                "tcp:8001",
                "tcp:8001",
            ],
            commands,
        )

    @patch("scripts.android.Path.is_file", return_value=True)
    @patch("scripts.android.subprocess.run")
    def test_no_saved_avd_explains_device_manager(self, run, exists):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "List of devices attached\n"),
            subprocess.CompletedProcess([], 0, ""),
        ]
        with self.assertRaisesRegex(RuntimeError, "Create one"):
            prepare("adb", "emulator", 8083)

    @patch("scripts.android.Path.open", new_callable=mock_open)
    @patch("scripts.android.Path.is_file", return_value=True)
    @patch("scripts.android.subprocess.Popen")
    @patch("scripts.android.subprocess.run")
    def test_starts_one_avd_then_waits_and_forwards(self, run, popen, exists, output):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "List of devices attached\n"),
            subprocess.CompletedProcess([], 0, "Pixel_Test\n"),
            subprocess.CompletedProcess(
                [], 0, "List of devices attached\nemulator-5554\tdevice\n"
            ),
            subprocess.CompletedProcess([], 0, "1\n"),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
        ]
        popen.return_value = MagicMock()
        prepare("adb", "emulator", 8083)
        self.assertEqual(popen.call_args.args[0], ["emulator", "-avd", "Pixel_Test"])


if __name__ == "__main__":
    unittest.main()
