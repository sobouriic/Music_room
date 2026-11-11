"""Authenticated speaker client. Run on the device with ffplay installed."""

import argparse
import asyncio
import getpass
import json
import shutil
import signal
import subprocess
from contextlib import suppress
from urllib.parse import urlparse
from uuid import UUID

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


class Speaker:
    def __init__(self):
        self.process = None
        self.url = None
        self.paused = False

    def stop(self):
        if self.process and self.process.poll() is None:
            if self.paused:
                self.process.send_signal(signal.SIGCONT)
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None
        self.url = None
        self.paused = False

    def apply(self, state):
        action = state.get("action", "stop")
        if action == "stop":
            self.stop()
            return
        if action == "pause":
            if self.process and self.process.poll() is None and not self.paused:
                self.process.send_signal(signal.SIGSTOP)
                self.paused = True
            return
        url = (state.get("track") or {}).get("preview_url")
        parsed = urlparse(url or "")
        if (
            action != "play"
            or parsed.scheme != "https"
            or not (parsed.hostname and parsed.hostname.endswith(".dzcdn.net"))
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            self.stop()
            raise ValueError("No trusted Deezer preview is available")
        if self.url == url and self.process and self.process.poll() is None:
            if self.paused:
                self.process.send_signal(signal.SIGCONT)
                self.paused = False
            return
        self.stop()
        self.process = subprocess.Popen(
            [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-protocol_whitelist",
                "https,tls,tcp,crypto",
                url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.url = url


async def run(args, password):
    speaker = Speaker()
    metadata = {"X-App-Platform": "iot", "X-App-Device": "speaker", "X-App-Version": "0.1.0"}
    async with httpx.AsyncClient(
        base_url=args.api.rstrip("/") + "/api/v1/",
        headers=metadata,
        timeout=15,
        follow_redirects=False,
    ) as http:
        login = await http.post("auth/login", json={"email": args.email, "password": password})
        if login.status_code != 200:
            raise RuntimeError("Unable to sign in. Verify the account and credentials.")
        tokens = login.json()

        async def refresh():
            nonlocal tokens
            response = await http.post(
                "auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
            if response.status_code != 200:
                raise RuntimeError("Speaker session was revoked. Sign in again.")
            tokens = response.json()

        async def request(method, path, **kwargs):
            response = await http.request(
                method,
                path,
                headers={"Authorization": "Bearer " + tokens["access_token"]},
                **kwargs,
            )
            if response.status_code == 401:
                await refresh()
                response = await http.request(
                    method,
                    path,
                    headers={"Authorization": "Bearer " + tokens["access_token"]},
                    **kwargs,
                )
            if response.status_code >= 400:
                raise RuntimeError(f"Speaker access refused (HTTP {response.status_code}).")
            return response.json()

        try:
            me = await request("GET", "users/me")
            device = (
                await request("GET", f"devices/{args.device_id}")
                if args.device_id
                else await request("POST", "devices", json={"name": args.name})
            )
            if device["owner_id"] != me["id"]:
                raise RuntimeError("Run the speaker using the device owner's account.")
            device_id = device["id"]
            print(
                f"Speaker device: {device_id}. Delegate it from Music Room's Control screen.",
                flush=True,
            )
            url = (
                args.api.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
            )
            failures = 0
            while True:
                try:
                    async with connect(
                        f"{url}/api/v1/ws/device/{device_id}",
                        additional_headers=metadata,
                        open_timeout=15,
                    ) as ws:
                        await ws.send(json.dumps({"access_token": tokens["access_token"]}))
                        async for raw in ws:
                            message = json.loads(raw)
                            if message.get("type") in {"ready", "device_changed"}:
                                device = await request("GET", f"devices/{device_id}")
                                speaker.apply(device["state"])
                                failures = 0
                except ConnectionClosed as exc:
                    speaker.stop()
                    if exc.rcvd and exc.rcvd.code == 1008:
                        await refresh()
                except (OSError, TimeoutError, httpx.TransportError):
                    speaker.stop()
                failures += 1
                if failures >= 5:
                    raise RuntimeError(
                        "Speaker disconnected repeatedly. Check connectivity and restart."
                    )
                await asyncio.sleep(min(2**failures, 15))
        finally:
            speaker.stop()
            with suppress(Exception):
                await http.post(
                    "auth/logout",
                    headers={"Authorization": "Bearer " + tokens["access_token"]},
                    json={"refresh_token": tokens["refresh_token"]},
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--email", required=True)
    parser.add_argument("--device-id", type=UUID)
    parser.add_argument("--name", default="Music Room speaker")
    args = parser.parse_args()
    if urlparse(args.api).scheme not in {"http", "https"}:
        parser.error("API URL must use HTTP or HTTPS")
    if not shutil.which("ffplay"):
        parser.error("Install FFmpeg (including ffplay) on this speaker device first")
    try:
        asyncio.run(run(args, getpass.getpass("Account password: ")))
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
