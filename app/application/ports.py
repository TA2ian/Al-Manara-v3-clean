from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.order import Order
from app.domain.order_status import OrderStatus


@dataclass(frozen=True, slots=True)
class PersistedOrderTransition:
    order: Order
    state_before: OrderStatus
    state_after: OrderStatus
    transitioned_at: datetime


class OrderRepository(Protocol):
    async def get_for_update(self, internal_order_id: UUID) -> Order | None: ...

    async def transition_if_version(
        self,
        internal_order_id: UUID,
        target_status: OrderStatus,
        expected_version: int,
        actor_telegram_user_id: int | None = None,
        actor_type: str | None = None,
        event_payload: dict[str, object] | None = None,
    ) -> PersistedOrderTransition | None: ...

    async def transition_idempotent(
        self,
        internal_order_id: UUID,
        target_status: OrderStatus,
        expected_version: int,
        actor_telegram_user_id: int,
        actor_type: str,
        idempotency_key: str,
        event_payload: dict[str, object] | None = None,
    ) -> PersistedOrderTransition | None: ...


class IdempotencyRepository(Protocol):
    async def get_result(self, key: str) -> PersistedOrderTransition | None: ...

    async def store_result(self, key: str, result: PersistedOrderTransition) -> None: ...
