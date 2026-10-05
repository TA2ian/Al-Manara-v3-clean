from uuid import uuid4

import pytest

from app.domain.exceptions import InvalidTransitionError
from app.domain.order import Order
from app.domain.order_status import OrderStatus, can_transition_order


def make_order(status: OrderStatus = OrderStatus.DRAFT, version: int = 1) -> Order:
    return Order(uuid4(), "ORD-TEST01", status, version)


def test_transition_matrix_matches_contract() -> None:
    expected = {
        OrderStatus.DRAFT: {OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED},
        OrderStatus.PENDING_PAYMENT: {
            OrderStatus.PAYMENT_SUBMITTED,
            OrderStatus.EXPIRED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.PAYMENT_SUBMITTED: {OrderStatus.UNDER_REVIEW},
        OrderStatus.UNDER_REVIEW: {
            OrderStatus.APPROVED,
            OrderStatus.REJECTED,
            OrderStatus.CLARIFICATION_REQUIRED,
        },
        OrderStatus.CLARIFICATION_REQUIRED: {
            OrderStatus.PAYMENT_SUBMITTED,
            OrderStatus.UNDER_REVIEW,
            OrderStatus.CANCELLED,
        },
        OrderStatus.APPROVED: {OrderStatus.CLOSED_WITHOUT_FULFILLMENT},
        OrderStatus.COMPLETED: set(),
        OrderStatus.CLOSED_WITHOUT_FULFILLMENT: set(),
        OrderStatus.REJECTED: set(),
        OrderStatus.CANCELLED: set(),
        OrderStatus.EXPIRED: set(),
    }

    for current, targets in expected.items():
        for target in OrderStatus:
            assert can_transition_order(current, target) is (target in targets)


def test_valid_transition_increments_version() -> None:
    order = make_order(OrderStatus.UNDER_REVIEW, version=7)

    updated = order.transition_to(OrderStatus.APPROVED)

    assert updated.status is OrderStatus.APPROVED
    assert updated.version == 8
    assert updated.internal_order_id == order.internal_order_id
    assert updated.public_order_code == order.public_order_code


def test_terminal_states_cannot_transition() -> None:
    for status in (
        OrderStatus.COMPLETED,
        OrderStatus.CLOSED_WITHOUT_FULFILLMENT,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    ):
        order = make_order(status)
        for target in OrderStatus:
            if target is status:
                continue
            with pytest.raises(InvalidTransitionError):
                order.transition_to(target)


def test_clarification_required_has_only_contract_transitions() -> None:
    order = make_order(OrderStatus.CLARIFICATION_REQUIRED)

    assert order.transition_to(OrderStatus.PAYMENT_SUBMITTED).version == 2
    assert order.transition_to(OrderStatus.UNDER_REVIEW).version == 2
    assert order.transition_to(OrderStatus.CANCELLED).version == 2

    for target in (
        OrderStatus.DRAFT,
        OrderStatus.PENDING_PAYMENT,
        OrderStatus.APPROVED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
        OrderStatus.COMPLETED,
        OrderStatus.CLOSED_WITHOUT_FULFILLMENT,
    ):
        with pytest.raises(InvalidTransitionError):
            order.transition_to(target)


def test_approved_cannot_transition_directly_to_completed() -> None:
    order = make_order(OrderStatus.APPROVED)

    with pytest.raises(InvalidTransitionError):
        order.transition_to(OrderStatus.COMPLETED)


def test_same_status_is_idempotent() -> None:
    order = make_order(OrderStatus.PENDING_PAYMENT, version=4)

    unchanged = order.transition_to(OrderStatus.PENDING_PAYMENT)

    assert unchanged is order
    assert unchanged.version == 4
