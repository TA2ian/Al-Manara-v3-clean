from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.exceptions import InvalidTransitionError
from app.domain.order_status import OrderStatus, can_transition_order


@dataclass(frozen=True, slots=True)
class OrderTransitionCommand:
    internal_order_id: UUID
    target_status: OrderStatus
    actor_id: int
    actor_type: str
    reason: str | None
    expected_version: int
    idempotency_key: str


def validate_transition_command(
    current_status: OrderStatus,
    command: OrderTransitionCommand,
) -> None:
    if command.expected_version < 1:
        raise ValueError("expected_version must be positive")
    if not command.idempotency_key.strip():
        raise ValueError("idempotency_key is required")
    if command.target_status == current_status:
        return
    # Administrative closure has mandatory session, reason, and fulfillment-
    # claim guards and must never be reachable through the generic transition.
    if command.target_status is OrderStatus.CLOSED_WITHOUT_FULFILLMENT:
        raise InvalidTransitionError(current_status.value, command.target_status.value)
    if not can_transition_order(current_status, command.target_status):
        raise InvalidTransitionError(current_status.value, command.target_status.value)
