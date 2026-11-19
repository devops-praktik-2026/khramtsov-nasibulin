"""Применить миграции только вперёд, сравнив ревизию БД с графом из wheel."""

import fcntl
import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from orders.db import engine


def remember_local_history(scripts: ScriptDirectory, path: Path) -> None:
    # Следующая установка локального wheel заменит содержимое /opt/orders/venv.
    history = json.loads(path.read_text()) if path.exists() else {}
    missing = [rev.revision for rev in scripts.walk_revisions() if rev.revision not in history]
    if missing:
        for revision in missing:
            lineage = scripts.iterate_revisions(revision, "base")
            history[revision] = [rev.revision for rev in lineage]
        pending = path.with_suffix(".tmp")
        pending.write_text(json.dumps(history))
        pending.replace(path)


def needs_upgrade(scripts: ScriptDirectory, current: str | None, releases: Path) -> bool:
    head = scripts.get_current_head()
    if not head:
        raise SystemExit("The release has no Alembic head")
    if current == head:
        return False
    if current is None or any(rev.revision == current for rev in scripts.walk_revisions()):
        return True

    local_history = releases.parent / ".local-migration-history.json"
    if local_history.exists() and head in json.loads(local_history.read_text()).get(current, []):
        return False

    # После обновления или неудачного перезапуска новый wheel остаётся на диске.
    # Только его граф может подтвердить, что текущая схема действительно новее.
    for marker in releases.glob("*/.sha256"):
        for path in marker.parent.glob("venv/lib/python*/site-packages/orders/migrations"):
            known = ScriptDirectory(str(path))
            if any(rev.revision == current for rev in known.walk_revisions()):
                if any(rev.revision == head for rev in known.iterate_revisions(current, "base")):
                    return False
    raise SystemExit(f"Database revision {current} has no verified migration path to {head}")


def main() -> None:
    venv = Path(sys.prefix)
    root = Path.cwd()  # chdir роли одинаков для локального venv и выпусков GitHub.
    scripts = ScriptDirectory(str(files("orders").joinpath("migrations")))
    with (root / ".migration.lock").open("a") as lock, engine.connect() as connection:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if venv == root / "venv":
            remember_local_history(scripts, root / ".local-migration-history.json")
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('orders.alembic'))"))
        current = MigrationContext.configure(connection).get_current_revision()
        if connection.dialect.name == "sqlite":
            connection.commit()  # Освободить читающую транзакцию для процесса Alembic.
        if needs_upgrade(scripts, current, root / "releases"):
            subprocess.run([venv / "bin/orders-migrate", "upgrade", "head"], check=True)
            print("upgraded")


if __name__ == "__main__":
    main()
