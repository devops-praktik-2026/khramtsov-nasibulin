"""Создание заказа через два настоящих HTTP-сервиса без подмены accounts."""

import os
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def running_service(name, tmp_path, **settings):
    """Применить миграции, запустить сервис и убрать процесс даже при ошибке."""
    service_dir = ROOT / "services" / name
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{(tmp_path / f'{name}.db').as_posix()}",
        "SERVICE_NAME": name,
        **settings,
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=service_dir,
        env=env,
        check=True,
        timeout=30,
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / f"{name}.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                f"{name}.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=service_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            with httpx.Client(timeout=0.5, trust_env=False) as client:
                while process.poll() is None and time.monotonic() < deadline:
                    try:
                        response = client.get(f"{url}/health")
                        if response.status_code == 200 and response.json() == {
                            "status": "ok",
                            "service": name,
                        }:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail(f"{name} не запустился:\n{log_path.read_text(encoding='utf-8')}")
            yield url
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


@pytest.fixture()
def services(tmp_path):
    with ExitStack() as stack:
        accounts_url = stack.enter_context(running_service("accounts", tmp_path))
        orders_url = stack.enter_context(
            running_service(
                "orders",
                tmp_path,
                ACCOUNTS_URL=accounts_url,
                ACCOUNTS_TIMEOUT_SECONDS="2",
            )
        )
        yield accounts_url, orders_url


def test_create_order_for_real_account(services):
    accounts_url, orders_url = services
    with httpx.Client(timeout=5, trust_env=False) as client:
        account_response = client.post(
            f"{accounts_url}/accounts",
            json={"name": "Иван", "email": "ivan@example.com"},
        )
        assert account_response.status_code == 201, account_response.text
        account_id = account_response.json()["id"]

        # Несуществующий клиент должен быть отклонён настоящим accounts.
        missing = client.post(
            f"{orders_url}/orders",
            json={"account_id": account_id + 1, "item": "Кофе", "quantity": 1},
        )
        assert missing.status_code == 404, missing.text

        payload = {"account_id": account_id, "item": "Кофе", "quantity": 2}
        response = client.post(f"{orders_url}/orders", json=payload)
        assert response.status_code == 201, response.text
        order = response.json()
        assert order.items() >= payload.items()
        assert order["id"] > 0
        assert order["created_at"]

        saved = client.get(f"{orders_url}/orders/{order['id']}")
        assert saved.status_code == 200, saved.text
        assert saved.json() == order
