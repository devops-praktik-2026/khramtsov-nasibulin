"""Запуск Alembic с конфигурацией и миграциями установленного orders."""

import sys
from importlib.resources import as_file, files

from alembic.config import main as alembic_main


def main() -> None:
    with as_file(files("orders").joinpath("migrations", "alembic.ini")) as config:
        alembic_main(prog="orders-migrate", argv=["-c", str(config), *sys.argv[1:]])
