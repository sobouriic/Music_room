"""Transactional mail outbox. Run with python -m mandatory.services.email_service."""

import argparse
import os
import time
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import digest, now, opaque
from app.db.session import lock_user, session_factory
from app.models.entities import ActionToken, MailJob


def queue_mail(db, user, kind):
    db.add(MailJob(user_id=user.id, kind=kind, auth_version=user.auth_version))


def deliver(recipient: str, kind: str, token: str):
    cfg = get_settings()
    message = EmailMessage()
    message["From"] = "noreply@music-room.local"
    message["To"] = recipient
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message["Message-ID"] = make_msgid()
    message["Subject"] = "Music Room: " + ("verify email" if kind == "verify" else "reset password")
    # Fragment avoids sending secrets to web server access logs; app/web handler reads it.
    action = "verify-email" if kind == "verify" else "reset-password"
    message.set_content(
        f"Open your Music Room app to {action}:\n"
        f"{cfg.email_link_base.rstrip('/')}/{action}#token={token}\n"
        "Or paste the token into Swagger's matching POST endpoint.\n"
        f"Token: {token}\n"
    )
    directory = Path(cfg.mail_directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / (opaque() + ".eml")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        file.write(message.as_string())


def process_one() -> bool:
    with session_factory()() as db:
        job = db.scalar(
            select(MailJob)
            .where(MailJob.next_attempt_at <= now())
            .order_by(MailJob.next_attempt_at, MailJob.created_at, MailJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return False
        user = lock_user(db, job.user_id)
        if (
            not user.disabled
            and (job.kind != "verify" or not user.verified)
            and (job.kind != "reset" or job.auth_version == user.auth_version)
        ):
            try:
                # Roll back an undelivered token without losing this job's lock.
                with db.begin_nested():
                    raw = opaque()
                    db.add(
                        ActionToken(
                            user_id=user.id,
                            kind=job.kind,
                            token_digest=digest(raw),
                            expires_at=now() + timedelta(hours=24 if job.kind == "verify" else 1),
                        )
                    )
                    db.flush()
                    deliver(user.email, job.kind, raw)
            except OSError as error:
                job.attempts += 1
                delay = min(30 * 2 ** min(job.attempts - 1, 7), 3600)
                job.next_attempt_at = now() + timedelta(seconds=delay)
                db.commit()
                # Exception text can expose private file paths or message contents.
                print(
                    f"Mail retry scheduled job={job.id} attempt={job.attempts} "
                    f"delay_seconds={delay} error={type(error).__name__}",
                    flush=True,
                )
                return True
        db.delete(job)
        db.commit()
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process currently due jobs once; future retries remain queued",
    )
    args = parser.parse_args()
    while True:
        try:
            processed = process_one()
        except Exception:
            # No exception contents: errors may expose private paths or message contents.
            print("Mail delivery failed; queued job retained for retry", flush=True)
            if args.once:
                raise SystemExit(1)
            time.sleep(10)
            continue
        if not processed:
            if args.once:
                break
            time.sleep(2)


if __name__ == "__main__":
    main()
