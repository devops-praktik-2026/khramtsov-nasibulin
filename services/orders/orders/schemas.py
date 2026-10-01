"""Описание того, что сервис принимает и что отдаёт.

Эти классы — не формальность. Из них FastAPI сам собирает документацию
по адресу /docs и сам проверяет входящие данные.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class BaseOrder(BaseModel):
    account_id: int
    item: str = Field(min_length=1, max_length=128, examples=["Кофе"])
    quantity: int = Field(gt=1)


class OrderCreate(BaseOrder):
    """Схема для создания заказа."""

    pass


class OrderRead(BaseOrder):
    """Схема самого заказа."""

    id: int
    created_at: datetime
