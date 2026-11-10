"""Проверка чистого запуска Compose и восстановления после отказа accounts."""

import json
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
HTTP = build_opener(ProxyHandler({}))


def request(url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    try:
        response = HTTP.open(Request(url, data=data, headers=headers), timeout=5)
    except HTTPError as error:
        response = error
    with response:
        body = response.read().decode("utf-8")
        try:
            return response.status, json.loads(body)
        except json.JSONDecodeError:
            return response.status, body


def wait_until_healthy(url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            status, _ = request(f"{url}/health")
            if status == 200:
                return
        except (OSError, URLError):
            pass
        time.sleep(0.2)
    raise AssertionError(f"Сервис не запустился: {url}")


class ComposeAvailabilityTest(unittest.TestCase):
    def test_order_creation_survives_accounts_restart(self):
        project = f"card24-{uuid.uuid4().hex[:12]}"
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / "ports.yaml"
            override.write_text(
                'services:\n  accounts:\n    ports: !override\n      - "127.0.0.1::8000"\n'
                '  orders:\n    ports: !override\n      - "127.0.0.1::8000"\n',
                encoding="utf-8",
            )
            compose = [
                "docker",
                "compose",
                "-p",
                project,
                "-f",
                str(ROOT / "compose.yaml"),
                "-f",
                str(override),
            ]

            def run_compose(*args):
                try:
                    result = subprocess.run(
                        [*compose, *args],
                        cwd=ROOT,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                except subprocess.CalledProcessError as error:
                    message = error.stderr or error.stdout
                    raise AssertionError(f"Docker Compose: {message}") from error
                return result.stdout.strip()

            try:
                run_compose("up", "--build", "-d")
                accounts = f"http://{run_compose('port', 'accounts', '8000')}"
                orders = f"http://{run_compose('port', 'orders', '8000')}"
                wait_until_healthy(accounts)
                wait_until_healthy(orders)

                status, account = request(
                    f"{accounts}/accounts", {"name": "Иван", "email": "ivan@example.com"}
                )
                self.assertEqual(status, 201, account)
                payload = {"account_id": account["id"], "item": "Кофе", "quantity": 1}
                status, order = request(f"{orders}/orders", payload)
                self.assertEqual(status, 201, order)

                run_compose("stop", "accounts")
                started = time.monotonic()
                status, error = request(f"{orders}/orders", payload)
                elapsed = time.monotonic() - started
                self.assertEqual(status, 503, error)
                self.assertLess(elapsed, 3, f"Ответ занял {elapsed:.2f} с")
                status, saved = request(f"{orders}/orders?account_id={account['id']}")
                self.assertEqual(status, 200, saved)
                self.assertEqual([item["id"] for item in saved], [order["id"]])

                run_compose("start", "accounts")
                # Docker может назначить новый случайный порт после перезапуска.
                accounts = f"http://{run_compose('port', 'accounts', '8000')}"
                wait_until_healthy(accounts)
                status, recovered = request(f"{orders}/orders", payload)
                self.assertEqual(status, 201, recovered)
            finally:
                run_compose("down", "-v", "--remove-orphans")


if __name__ == "__main__":
    unittest.main()
