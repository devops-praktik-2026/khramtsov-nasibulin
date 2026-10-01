"""Общая подготовка для тестов сервиса заказов.

Каждый тест получает свою пустую базу данных в оперативной памяти.
Так тесты не зависят друг от друга и не требуют запущенного PostgreSQL.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orders.db import Base, get_session
from orders.main import app


@dataclass
class AccountsServiceStub:
    status_code: int = 200
    error: type[httpx.RequestError] | None = None
    requests: list[httpx.Request] = field(default_factory=list)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error("Сервис клиентов недоступен", request=request)
        return httpx.Response(
            self.status_code,
            json={
                "id": int(request.url.path.rsplit("/", 1)[-1]),
                "name": "Иван",
                "email": "ivan@example.com",
                "created_at": "2026-10-01T10:00:00Z",
            },
        )


@pytest.fixture()
def accounts_service(monkeypatch) -> AccountsServiceStub:
    service = AccountsServiceStub()
    transport = httpx.MockTransport(service.handle_request)
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "handle_request",
        lambda self, request: transport.handle_request(request),
    )
    return service


@pytest.fixture()
def client(accounts_service) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def order_payload() -> dict:
    return {"account_id": 1, "item": "cool-item", "quantity": 1}
