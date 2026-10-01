"""Список заказов клиента: фильтрация, пагинация и проверка параметров."""

from contextlib import contextmanager
from datetime import datetime

import pytest

from orders.db import get_session
from orders.main import app
from orders.models import Order


@pytest.fixture()
def insert_orders(client):
    """Заполняет настоящую тестовую БД независимо от создания заказа через API."""

    def insert(rows):
        with contextmanager(app.dependency_overrides[get_session])() as session:
            session.add_all(rows)
            session.commit()

    return insert


@pytest.fixture()
def stored_orders(insert_orders):
    insert_orders(
        [
            Order(id=30, account_id=7, item="Кофе", quantity=1),
            Order(id=10, account_id=7, item="Чай", quantity=2),
            Order(id=20, account_id=8, item="Чужой заказ", quantity=3),
            Order(id=40, account_id=7, item="Какао", quantity=2),
        ]
    )


def test_list_returns_only_client_orders_in_id_order(client, stored_orders):
    response = client.get("/orders", params={"account_id": 7})

    assert response.status_code == 200
    body = response.json()
    assert [order["id"] for order in body] == [10, 30, 40]
    assert all(order["account_id"] == 7 for order in body)
    assert [order["item"] for order in body] == ["Чай", "Кофе", "Какао"]


def test_list_returns_complete_card_with_quantity_one(client, insert_orders):
    insert_orders(
        [
            Order(
                id=1,
                account_id=7,
                item="Кофе",
                quantity=1,
                created_at=datetime(2026, 10, 1, 10, 0),
            )
        ]
    )

    response = client.get("/orders", params={"account_id": 7})

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "account_id": 7,
            "item": "Кофе",
            "quantity": 1,
            "created_at": "2026-10-01T10:00:00",
        }
    ]


def test_list_empty_database_returns_empty_list(client):
    response = client.get("/orders", params={"account_id": 7})

    assert response.status_code == 200
    assert response.json() == []


def test_list_client_without_orders_returns_empty_list(client, stored_orders):
    response = client.get("/orders", params={"account_id": 999})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    ("pagination", "expected_ids"),
    [
        ({"limit": 1}, [10]),
        ({"limit": 2}, [10, 30]),
        ({"limit": 1, "offset": 1}, [30]),
        ({"offset": 2}, [40]),
        ({"offset": 3}, []),
        ({"limit": 200, "offset": 0}, [10, 30, 40]),
    ],
)
def test_list_paginates_after_filtering(client, stored_orders, pagination, expected_ids):
    response = client.get("/orders", params={"account_id": 7} | pagination)

    assert response.status_code == 200
    assert [order["id"] for order in response.json()] == expected_ids


def test_list_default_limit_is_fifty(client, insert_orders):
    insert_orders(
        [Order(id=number, account_id=7, item="Чай", quantity=2) for number in range(1, 52)]
    )

    response = client.get("/orders", params={"account_id": 7})

    assert response.status_code == 200
    assert [order["id"] for order in response.json()] == list(range(1, 51))


@pytest.mark.parametrize(
    ("params", "invalid_field"),
    [
        ({}, "account_id"),
        ({"account_id": 0}, "account_id"),
        ({"account_id": -1}, "account_id"),
        ({"account_id": "bad"}, "account_id"),
        ({"account_id": "1.5"}, "account_id"),
        ({"account_id": 7, "limit": 0}, "limit"),
        ({"account_id": 7, "limit": -1}, "limit"),
        ({"account_id": 7, "limit": 201}, "limit"),
        ({"account_id": 7, "limit": "bad"}, "limit"),
        ({"account_id": 7, "limit": "1.5"}, "limit"),
        ({"account_id": 7, "offset": -1}, "offset"),
        ({"account_id": 7, "offset": "bad"}, "offset"),
        ({"account_id": 7, "offset": "1.5"}, "offset"),
    ],
)
def test_list_invalid_query_returns_422_with_field(client, params, invalid_field):
    response = client.get("/orders", params=params)

    assert response.status_code == 422
    assert ["query", invalid_field] in [error["loc"] for error in response.json()["detail"]]
