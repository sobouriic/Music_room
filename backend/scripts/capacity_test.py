"""Isolated mixed HTTP/WebSocket ramp-up. Never accepts the development database."""

import argparse
import asyncio
import json
import os
import platform
import secrets
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from websockets.asyncio.client import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--output", default="docs/CAPACITY_RESULTS.json")
    args = parser.parse_args()
    if any(n < 1 or n > 100 for n in args.users) or not 2 <= args.seconds <= 60:
        parser.error("Use 1–100 users and 2–60 seconds per stage")
    database = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://music:music_test_only@localhost:5433/music_room_test",
    )
    if not (make_url(database).database or "").endswith("_test"):
        parser.error("TEST_DATABASE_URL must end in _test")
    # Controlled capacity profile: isolate the app's throughput from per-IP abuse limits.
    # Default production limits are measured separately by security tests, not disabled globally.
    os.environ.update(
        DATABASE_URL=database,
        APP_ENV="test",
        JWT_SECRET=secrets.token_urlsafe(48),
        MUSIC_RATE_LIMIT="100000",
        RATE_LIMIT="100000",
    )
    from alembic.config import Config

    from alembic import command
    from app.core.security import access_token, digest, now
    from app.db.session import session_factory
    from app.models.entities import MusicResource, PlaybackDevice, Profile, RefreshSession, User

    command.upgrade(Config("alembic.ini"), "head")
    people = []
    owner = uuid4()
    resource = uuid4()
    event = uuid4()
    tracks = [
        {
            "id": str(uuid4()),
            "deezer_id": i + 1,
            "title": f"Test {i}",
            "artist": "Synthetic",
            "duration": 30,
            "preview_url": None,
            "artwork_url": None,
            "deezer_url": None,
        }
        for i in range(3)
    ]
    user_ids = [owner] + [uuid4() for _ in range(max(args.users) - 1)]
    with session_factory()() as db:
        for uid in user_ids:
            user = User(
                id=uid,
                email=f"{uid}@capacity.invalid",
                verified=True,
                plan="premium",
                password_hash=None,
            )
            db.add(user)
        db.flush()
        for uid in user_ids:
            sid, device = uuid4(), uuid4()
            db.add(Profile(user_id=uid))
            db.add(
                RefreshSession(
                    id=sid,
                    user_id=uid,
                    token_digest=digest(secrets.token_urlsafe(32)),
                    expires_at=now() + timedelta(hours=1),
                )
            )
            db.add(PlaybackDevice(id=device, owner_id=uid, name="Capacity device"))
            people.append((access_token(uid, sid, 0), str(device)))
        db.add(
            MusicResource(
                id=resource,
                owner_id=owner,
                kind="playlist",
                name="Capacity shared editor",
                tracks=tracks,
            )
        )
        db.add(
            MusicResource(
                id=event, owner_id=owner, kind="event", name="Capacity shared votes", tracks=tracks
            )
        )
        db.commit()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}/api/v1"
    logs = tempfile.TemporaryFile()
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
            "--log-level",
            "warning",
        ],
        stdout=logs,
        stderr=logs,
    )

    async def stage(count):
        statuses = Counter()
        timings = []
        ws_count = 0
        deadline = time.monotonic() + args.seconds

        async def user(index):
            nonlocal ws_count
            token, device = people[index]
            headers = {
                "Authorization": f"Bearer {token}",
                "X-App-Platform": "load-test",
                "X-App-Device": "synthetic",
                "X-App-Version": "0.1.0",
            }
            async with httpx.AsyncClient(base_url=base, headers=headers, timeout=15) as client:
                async with connect(f"ws://127.0.0.1:{port}/api/v1/ws/playlist/{resource}") as ws:
                    await ws.send(
                        json.dumps(
                            {
                                "access_token": token,
                                "metadata": {
                                    "platform": "load-test",
                                    "device": "synthetic",
                                    "app_version": "0.1.0",
                                },
                            }
                        )
                    )
                    if json.loads(await ws.recv()).get("type") == "ready":
                        ws_count += 1

                    async def call(method, path, **kwargs):
                        begin = time.monotonic()
                        try:
                            response = await client.request(method, path, **kwargs)
                            statuses[str(response.status_code)] += 1
                            return response
                        except httpx.HTTPError:
                            statuses["network_error"] += 1
                            return None
                        finally:
                            timings.append((time.monotonic() - begin) * 1000)

                    while time.monotonic() < deadline:
                        await call(
                            "POST",
                            f"/events/{event}/tracks/{tracks[index % 3]['id']}/votes",
                            json={},
                        )
                        await call(
                            "DELETE",
                            f"/events/{event}/tracks/{tracks[index % 3]['id']}/votes",
                            json={},
                        )
                        response = await call("GET", f"/playlists/{resource}")
                        if response is not None and response.status_code == 200:
                            await call(
                                "POST",
                                f"/playlists/{resource}/tracks/move",
                                json={
                                    "base_version": response.json()["version"],
                                    "from_index": 0,
                                    "to_index": 1,
                                },
                            )
                        response = await call("GET", f"/devices/{device}")
                        if response is not None and response.status_code == 200:
                            await call(
                                "POST",
                                f"/devices/{device}/control",
                                json={
                                    "base_version": response.json()["version"],
                                    "action": "pause",
                                },
                            )
                        await asyncio.sleep(0.2)

        begin = time.monotonic()
        await asyncio.gather(*(user(i) for i in range(count)))
        elapsed = time.monotonic() - begin
        timings.sort()
        return {
            "users": count,
            "websockets_ready": ws_count,
            "elapsed_seconds": round(elapsed, 2),
            "requests": len(timings),
            "rps": round(len(timings) / elapsed, 2),
            "median_ms": round(statistics.median(timings), 2),
            "p95_ms": round(timings[max(0, int(len(timings) * 0.95) - 1)], 2),
            "statuses": dict(statuses),
            "unexpected_errors": sum(
                n for code, n in statuses.items() if code not in ("200", "201", "204", "409")
            ),
        }

    try:
        for _ in range(100):
            try:
                if httpx.get(base + "/health", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if server.poll() is not None:
                raise RuntimeError("Capacity API did not start")
            time.sleep(0.1)
        results = [asyncio.run(stage(n)) for n in args.users]
        memory = (
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
            if sys.platform == "darwin"
            else str(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
        )
        report = {
            "measured_at": now().isoformat(),
            "host": {
                "os": platform.platform(),
                "machine": platform.machine(),
                "logical_cpus": os.cpu_count(),
                "host_ram_bytes": int(memory),
            },
            "deployment": "one local Uvicorn worker + Docker PostgreSQL 17; generator on same host",
            "profile": (
                "Synthetic 3-track shared playlist/event; one device and one persistent "
                "WebSocket per user; vote/unvote, competing playlist moves, device pause; "
                "200ms think time; no provider/audio transfer "
            ),
            "rate_limits": (
                "Isolated process MUSIC_RATE_LIMIT=100000 and RATE_LIMIT=100000 per 300s; "
                "default deployment limits remain enabled. This measures throughput, not "
                "admission under defaults. "
            ),
            "conflicts": (
                "409 is an expected, safely rejected stale playlist move; clients refetch "
                "next iteration "
            ),
            "stages": results,
            "interpretation": (
                "Tested short-run concurrency bound only, not a universal maximum or "
                "endurance claim. Repeat on the deployment server with representative data "
                "and normal admission policies. "
            ),
        }
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        logs.close()
        with session_factory()() as db:
            db.execute(delete(User).where(User.id.in_(user_ids)))
            db.commit()


if __name__ == "__main__":
    main()
