import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import hasher, verify_password


def test_password_verification_and_argon2id():
    hashed = hasher.hash("a long password 42!")
    assert hashed.startswith("$argon2id$")
    assert verify_password("a long password 42!", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("wrong", None)
    assert not verify_password("wrong", "invalid-hash")


def test_production_rejects_insecure_configuration():
    with pytest.raises(ValidationError):
        Settings(app_env="production", email_link_base="http://localhost:8000")
    with pytest.raises(ValidationError):
        Settings(jwt_secret="short")
