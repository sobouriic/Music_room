from email import policy
from email.parser import Parser
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.entities import ActionToken, MailJob
from mandatory.services.email_service import deliver, process_one
from tests.conftest import EMAIL, PASSWORD


def test_local_delivery_saves_private_message_with_token():
    deliver(EMAIL, "verify", "test-token")
    paths = list(Path(get_settings().mail_directory).glob("*.eml"))
    assert len(paths) == 1
    assert paths[0].stat().st_mode & 0o777 == 0o600
    message = Parser(policy=policy.default).parsestr(paths[0].read_text())
    assert message["To"] == EMAIL
    assert message["Date"] and message["Message-ID"]
    assert "Token: test-token" in message.get_content()


def test_delivery_failure_retains_outbox_and_rolls_back_token(client, db, monkeypatch):
    client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})

    def failure(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("mandatory.services.email_service.deliver", failure)
    assert process_one()
    job = db.scalar(select(MailJob))
    assert job.attempts == 1
    from app.core.security import now

    assert job.next_attempt_at > now()
    assert not process_one()
    assert db.scalar(select(func.count()).select_from(MailJob)) == 1
    assert db.scalar(select(func.count()).select_from(ActionToken)) == 0


def test_queued_recovery_is_discarded_after_password_change(client, db):
    from tests.conftest import account, headers

    pair = account(client)
    client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers(pair),
        json={"current_password": PASSWORD, "password": "An entirely new password 46!"},
    )
    assert response.status_code == 200
    before = db.scalar(select(func.count()).select_from(ActionToken))
    assert process_one()
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(ActionToken)) == before
    assert db.scalar(select(func.count()).select_from(MailJob)) == 0


def test_failed_recipient_does_not_block_other_users(client, db, monkeypatch, capsys):
    for email in (EMAIL, "bob@example.com"):
        client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    delivered = []

    def send(recipient, kind, token):
        if recipient == EMAIL:
            raise PermissionError("private file path")
        delivered.append(recipient)

    monkeypatch.setattr("mandatory.services.email_service.deliver", send)
    assert process_one()
    assert process_one()
    assert delivered == ["bob@example.com"]
    assert not process_one()
    assert db.scalar(select(func.count()).select_from(ActionToken)) == 1
    job = db.scalar(select(MailJob))
    assert job.attempts == 1
    from datetime import timedelta

    from app.core.security import now

    job.next_attempt_at = now() - timedelta(seconds=1)
    db.commit()
    assert process_one()
    db.refresh(job)
    assert job.attempts == 2
    assert job.next_attempt_at > now() + timedelta(seconds=50)
    log = capsys.readouterr().out
    assert "PermissionError" in log
    assert EMAIL not in log and "private file path" not in log
