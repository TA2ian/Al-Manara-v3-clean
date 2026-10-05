from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.order_service import OrderTransitionService
from app.application.ports import PersistedOrderTransition
from app.domain.order_status import OrderStatus
from app.domain.order_transition import OrderTransitionCommand

MIN_REASON_LENGTH = 5
MAX_REASON_LENGTH = 1000
ADMIN_ACTOR_TYPES = frozenset({"primary", "backup"})


class AdminAuthorizationPort(Protocol):
    async def authorize(self, telegram_user_id: int, actor_type: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class AdminReviewOrderCommand:
    internal_order_id: UUID
    actor_telegram_user_id: int
    actor_type: str
    expected_version: int
    action: str
    reason: str | None = None
    idempotency_key: str = ""


class AdminOrderReviewService:
    """Application boundary for human admin review of a submitted payment."""

    def __init__(self, transitions: OrderTransitionService, authorization: AdminAuthorizationPort) -> None:
        self._transitions = transitions
        self._authorization = authorization

    async def review(self, command: AdminReviewOrderCommand) -> PersistedOrderTransition:
        if not isinstance(command.internal_order_id, UUID):
            raise ValueError("order id is required")
        if not isinstance(command.actor_telegram_user_id, int) or command.actor_telegram_user_id <= 0:
            raise ValueError("admin telegram user id must be positive")
        if not isinstance(command.actor_type, str):
            raise ValueError("admin actor type is required")
        actor_type = command.actor_type.strip().lower()
        if actor_type not in ADMIN_ACTOR_TYPES:
            raise ValueError("unsupported admin actor type")
        if not isinstance(command.expected_version, int) or command.expected_version < 1:
            raise ValueError("expected version must be positive")
        if not isinstance(command.action, str):
            raise ValueError("review action is required")
        if not isinstance(command.idempotency_key, str):
            raise ValueError("idempotency key is required")

        if not await self._authorization.authorize(command.actor_telegram_user_id, actor_type):
            raise PermissionError("admin is not authorized for order review")

        action = command.action.strip().lower()
        targets = {
            "approve": OrderStatus.APPROVED,
            "reject": OrderStatus.REJECTED,
            "clarify": OrderStatus.CLARIFICATION_REQUIRED,
        }
        target = targets.get(action)
        if target is None:
            raise ValueError("unsupported admin review action")

        if command.reason is not None and not isinstance(command.reason, str):
            raise ValueError("review reason is invalid")
        reason = " ".join((command.reason or "").split())
        if target in {OrderStatus.REJECTED, OrderStatus.CLARIFICATION_REQUIRED}:
            if not MIN_REASON_LENGTH <= len(reason) <= MAX_REASON_LENGTH:
                raise ValueError(
                    f"review reason must be between {MIN_REASON_LENGTH} and {MAX_REASON_LENGTH} characters"
                )
        else:
            reason = None

        idempotency_key = command.idempotency_key.strip()
        if not 1 <= len(idempotency_key) <= 128:
            raise ValueError("idempotency key must be between 1 and 128 characters")

        transition = OrderTransitionCommand(
            internal_order_id=command.internal_order_id,
            target_status=target,
            actor_id=command.actor_telegram_user_id,
            actor_type=actor_type,
            reason=reason,
            expected_version=command.expected_version,
            idempotency_key=idempotency_key,
        )
        return await self._transitions.transition_order(transition)
