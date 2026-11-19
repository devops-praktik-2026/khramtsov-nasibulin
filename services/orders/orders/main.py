"""Точка входа сервиса заказов.

Запуск вручную:
    uvicorn orders.main:app --reload --port 8002
"""

from fastapi import FastAPI
from pydantic import BaseModel

from orders import __version__
from orders.api import router as api_order
from orders.config import settings

app = FastAPI(
    title="Сервис заказов",
    description="Заготовка.",
    version=__version__,
)

app.include_router(api_order)


class HealthRead(BaseModel):
    status: str
    service: str
    version: str


@app.get("/health", response_model=HealthRead, tags=["Служебное"], summary="Жив ли сервис")
def health() -> HealthRead:
    return HealthRead(status="ok", service=settings.service_name, version=__version__)


# TODO Изменить description (пример задачи)
