"""Проверка существования клиента через HTTP API сервиса клиентов."""

import httpx
from fastapi import HTTPException, status

from orders.config import settings


def ensure_account_exists(account_id: int) -> None:
    url = f"{settings.accounts_url.rstrip('/')}/accounts/{account_id}"
    try:
        response = httpx.get(url, timeout=settings.accounts_timeout_seconds)
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис клиентов временно недоступен",
        ) from None

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Клиент {account_id} не найден",
        )
    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис клиентов временно недоступен",
        )
