"""Установленный orders-migrate работает из любого каталога с базой из DATABASE_URL."""

import shutil
import sqlite3
import subprocess
import sys
import sysconfig

import pytest

from orders import config
from orders.migrate import main


@pytest.fixture()
def migration_cli(tmp_path, monkeypatch):
    database = tmp_path / "orders.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}?timeout=%35")

    def run(*args):
        executable = shutil.which("orders-migrate", path=sysconfig.get_path("scripts"))
        assert executable is not None, "У пакета orders должна быть команда orders-migrate"
        return subprocess.run(
            [executable, *args], check=True, capture_output=True, text=True, timeout=30
        ).stdout

    return database, run


def test_migrate_uses_packaged_revisions_and_configured_database(migration_cli):
    database, migrate = migration_cli
    migrate("upgrade", "head")
    migrate("upgrade", "head")
    with sqlite3.connect(database) as connection:
        (revision,) = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert connection.execute("SELECT count(*) FROM orders").fetchone() == (0,)
    assert revision in migrate("current")

    migrate("downgrade", "base")
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA table_info(orders)").fetchall() == []


def test_migrate_can_preview_sql_without_opening_the_database(migration_cli, monkeypatch, capsys):
    database, _ = migration_cli
    monkeypatch.setattr(config, "settings", config.Settings())
    monkeypatch.setattr(sys, "argv", ["orders-migrate", "upgrade", "head", "--sql"])
    main()
    assert "CREATE TABLE orders" in capsys.readouterr().out
    assert not database.exists()
