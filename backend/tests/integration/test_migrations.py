from alembic.config import Config

from alembic import command


def test_migrations_roundtrip_and_model_consistency(database):
    # conftest refuses destructive tests unless the isolated DB name ends with _test.
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)
