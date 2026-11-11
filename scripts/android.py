"""Connect one Android device, optionally boot an AVD, and forward local ports."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def devices(adb):
    result = subprocess.run(
        [adb, "devices"], check=True, capture_output=True, text=True
    )
    return [
        tuple(line.split()[:2])
        for line in result.stdout.splitlines()[1:]
        if len(line.split()) >= 2
    ]


def choose_device(rows, serial=None):
    if serial:
        matches = [row for row in rows if row[0] == serial]
        if not matches:
            raise RuntimeError(f"Android device {serial} is not connected.")
        if matches[0][1] != "device":
            raise RuntimeError(
                f"Device {serial} is {matches[0][1]}. Unlock/authorize it first."
            )
        return serial
    ready = [serial for serial, state in rows if state == "device"]
    if len(ready) > 1:
        raise RuntimeError(
            "Multiple Android devices connected. Use ANDROID_SERIAL=" + ready[0]
        )
    if ready:
        return ready[0]
    if rows:
        raise RuntimeError(
            "Android is offline or unauthorized. Unlock/authorize it, or restart the emulator."
        )
    return None


def prepare(adb, emulator, metro_port, serial=None, avd=None, timeout=180):
    selected = choose_device(devices(adb), serial)
    if not selected:
        if not Path(emulator).is_file():
            raise RuntimeError(
                "Open Android Studio → Device Manager → start a virtual phone, then retry."
            )
        result = subprocess.run(
            [emulator, "-list-avds"], check=True, capture_output=True, text=True
        )
        names = result.stdout.split()
        if not names:
            raise RuntimeError(
                "No Android virtual phone exists. Create one in Android Studio → Device Manager."
            )
        if avd and avd not in names:
            raise RuntimeError("Unknown ANDROID_AVD. Available: " + ", ".join(names))
        if not avd and len(names) > 1:
            raise RuntimeError(
                "Choose a virtual phone: make android ANDROID_AVD="
                + names[0]
                + " (available: "
                + ", ".join(names)
                + ")"
            )
        name = avd or names[0]
        print("Starting Android emulator " + name + "…", flush=True)
        log = Path(os.environ.get("TMPDIR", "/tmp")) / "music-room-emulator.log"
        with log.open("a") as output:
            process = subprocess.Popen(
                [emulator, "-avd", name],
                stdout=output,
                stderr=output,
                start_new_session=True,
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = devices(adb)
            ready = [
                value
                for value, state in rows
                if state == "device" and value.startswith("emulator-")
            ]
            if len(ready) == 1:
                selected = ready[0]
                break
            if process.poll() is not None:
                raise RuntimeError("Emulator exited. See " + str(log))
            time.sleep(2)
        if not selected:
            raise RuntimeError(
                "Emulator did not connect in time. Start it in Device Manager and retry. Log: "
                + str(log)
            )
    print("Waiting for Android " + selected + " to finish booting…", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            [adb, "-s", selected, "shell", "getprop", "sys.boot_completed"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip() == "1":
            break
        time.sleep(2)
    else:
        raise RuntimeError(
            "Android boot timed out. Wait for its home screen, then retry."
        )
    for port in (metro_port, 8001):
        subprocess.run(
            [adb, "-s", selected, "reverse", f"tcp:{port}", f"tcp:{port}"], check=True
        )
    print("Android ready: " + selected, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--metro-port", type=int, default=8083)
    parser.add_argument("--serial")
    parser.add_argument("--avd")
    args = parser.parse_args()
    emulator = str(Path(args.adb).parent.parent / "emulator" / "emulator")
    try:
        prepare(args.adb, emulator, args.metro_port, args.serial, args.avd)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print("Android setup: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
