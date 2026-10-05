from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"
    CLOSED_WITHOUT_FULFILLMENT = "CLOSED_WITHOUT_FULFILLMENT"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.DRAFT: frozenset({OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED}),
    OrderStatus.PENDING_PAYMENT: frozenset(
        {OrderStatus.PAYMENT_SUBMITTED, OrderStatus.EXPIRED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PAYMENT_SUBMITTED: frozenset({OrderStatus.UNDER_REVIEW}),
    OrderStatus.UNDER_REVIEW: frozenset(
        {OrderStatus.APPROVED, OrderStatus.REJECTED, OrderStatus.CLARIFICATION_REQUIRED}
    ),
    OrderStatus.CLARIFICATION_REQUIRED: frozenset(
        {OrderStatus.PAYMENT_SUBMITTED, OrderStatus.UNDER_REVIEW, OrderStatus.CANCELLED}
    ),
    # COMPLETED is deliberately excluded from the generic state machine.
    # It is reached only through the atomic fulfillment completion operation.
    OrderStatus.APPROVED: frozenset({OrderStatus.CLOSED_WITHOUT_FULFILLMENT}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CLOSED_WITHOUT_FULFILLMENT: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.EXPIRED: frozenset(),
}


def allowed_order_transitions(status: OrderStatus) -> frozenset[OrderStatus]:
    return _ALLOWED_TRANSITIONS[status]


def can_transition_order(current: OrderStatus, target: OrderStatus) -> bool:
    return target in allowed_order_transitions(current)
