import pytest
from fastapi.testclient import TestClient


def test_create_order_returns_201(client: TestClient):
    payload = {"account_id": 1, "item": "Кофемолка", "quantity": 2}

    response = client.post("/orders", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["account_id"] == payload["account_id"]
    assert body["item"] == payload["item"]
    assert body["quantity"] == payload["quantity"]


@pytest.mark.parametrize(
    "broken_field",
    argvalues=[
        {"quantity": "это-не-число"},
        {"quantity": 0},
        {"quantity": -1},
        {"account_id": "это-не-число"},
    ],
)
def test_invalid_payload_returns_422(client, order_payload, broken_field):
    payload = order_payload | broken_field

    response = client.post("/orders", json=payload)

    assert response.status_code == 422
