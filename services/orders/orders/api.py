"""Запросы, которые умеет обрабатывать сервис заказов."""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from orders.db import get_session
from orders.models import Order
from orders.schemas import OrderCreate, OrderRead

router = APIRouter(prefix="/orders", tags=["Заказы"])


def _get_or_404(session: Session, order_id: int) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Заказ {order_id} не найден",
        )

    return order


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заказ",
)
def create_order(payload: OrderCreate, session: Session = Depends(get_session)) -> Order:
    order = Order(**payload.model_dump())
    session.add(order)
    session.commit()

    session.refresh(order)

    return order


@router.get("/{order_id}", response_model=OrderRead, summary="Получить заказ")
def get_order(
    order_id: int = Path(ge=1, le=2**63 - 1), session: Session = Depends(get_session)
) -> Order:
    return _get_or_404(session, order_id)

@router.get("", response_model=list[OrderRead], summary="Список заказов клиента")
def list_orders(
    account_id: int = Query(..., ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.account_id == account_id)
        .order_by(Order.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(stmt))
