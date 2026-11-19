"""Проверяем состояние и установленную версию сервиса заказов."""

from importlib.metadata import version

from fastapi.testclient import TestClient

from orders.main import app

client = TestClient(app)


def test_health_reports_installed_version():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "orders", "version": version("orders")}
