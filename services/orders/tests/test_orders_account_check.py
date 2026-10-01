"""Проверка клиента должна завершиться до сохранения заказа."""

import httpx
import pytest

from orders.config import settings


@pytest.mark.parametrize("base_url", ["http://accounts.test/api", "http://accounts.test/api/"])
def test_create_order_checks_account_using_configured_url_and_timeout(
    client, accounts_service, monkeypatch, base_url
):
    monkeypatch.setattr(settings, "accounts_url", base_url)
    monkeypatch.setattr(settings, "accounts_timeout_seconds", 0.4)

    response = client.post("/orders", json={"account_id": 7, "item": "Кофе", "quantity": 1})

    assert response.status_code == 201
    assert response.json()["account_id"] == 7
    assert len(accounts_service.requests) == 1
    request = accounts_service.requests[0]
    assert request.method == "GET"
    assert str(request.url) == "http://accounts.test/api/accounts/7"
    assert request.extensions["timeout"] == {
        "connect": 0.4,
        "read": 0.4,
        "write": 0.4,
        "pool": 0.4,
    }
    saved = client.get(f"/orders/{response.json()['id']}")
    assert saved.status_code == 200
    assert saved.json() == response.json()


def test_missing_account_returns_404_without_saving_order(client, accounts_service):
    accounts_service.status_code = 404

    response = client.post("/orders", json={"account_id": 7, "item": "Кофе", "quantity": 1})

    assert response.status_code == 404
    assert response.json() == {"detail": "Клиент 7 не найден"}
    orders = client.get("/orders", params={"account_id": 7})
    assert orders.status_code == 200
    assert orders.json() == []
    assert client.get("/orders/1").status_code == 404


@pytest.mark.parametrize("status_code", [201, 204, 302, 401, 500, 503])
def test_unexpected_account_response_returns_503_without_saving_order(
    client, accounts_service, status_code
):
    accounts_service.status_code = status_code

    response = client.post("/orders", json={"account_id": 7, "item": "Кофе", "quantity": 1})

    assert response.status_code == 503
    assert response.json() == {"detail": "Сервис клиентов временно недоступен"}
    assert client.get("/orders", params={"account_id": 7}).json() == []


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_accounts_network_error_returns_503_without_saving_order(client, accounts_service, error):
    accounts_service.error = error

    response = client.post("/orders", json={"account_id": 7, "item": "Кофе", "quantity": 1})

    assert response.status_code == 503
    assert response.json() == {"detail": "Сервис клиентов временно недоступен"}
    assert client.get("/orders", params={"account_id": 7}).json() == []


def test_invalid_order_does_not_contact_accounts(client, accounts_service):
    response = client.post("/orders", json={"account_id": 7, "item": "Кофе", "quantity": 0})

    assert response.status_code == 422
    assert accounts_service.requests == []
