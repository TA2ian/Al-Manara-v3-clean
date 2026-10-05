from __future__ import annotations

from typing import Protocol, Self

from app.application.ports import IdempotencyRepository, OrderRepository


class UnitOfWork(Protocol):
    orders: OrderRepository
    idempotency: IdempotencyRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
