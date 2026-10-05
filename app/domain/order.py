from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.exceptions import InvalidTransitionError
from app.domain.order_status import OrderStatus, can_transition_order


@dataclass(frozen=True, slots=True)
class Order:
    internal_order_id: UUID
    public_order_code: str
    status: OrderStatus
    version: int

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("order version must be non-negative")

    def transition_to(self, target: OrderStatus) -> Order:
        if target == self.status:
            return self
        if not can_transition_order(self.status, target):
            raise InvalidTransitionError(self.status.value, target.value)
        return Order(
            internal_order_id=self.internal_order_id,
            public_order_code=self.public_order_code,
            status=target,
            version=self.version + 1,
        )
