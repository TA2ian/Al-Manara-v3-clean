from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.application.ports import IdempotencyRepository, PersistedOrderTransition
from app.application.uow import UnitOfWork
from app.infrastructure.persistence.order_repository import SupabaseOrderRepository


class SupabaseOrderRpcClient(Protocol):
    def rpc(self, function_name: str, params: dict[str, Any]) -> Any: ...


class SupabaseOrderUnitOfWork(UnitOfWork):
    """Composition adapter for order transitions whose transaction is owned by PostgreSQL RPCs.

    The authoritative transition, authorization, idempotency reservation, row lock,
    audit write, and commit all occur inside ``transition_order_idempotent``.  The
    application-level UoW therefore deliberately does not open a second HTTP-level
    transaction around those calls.
    """

    def __init__(self, client: SupabaseOrderRpcClient) -> None:
        self.orders = SupabaseOrderRepository(client)
        self.idempotency: IdempotencyRepository = _RpcOwnedIdempotencyRepository()

    async def __aenter__(self) -> "SupabaseOrderUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        # Each authoritative Supabase RPC executes and commits its own DB transaction.
        return None

    async def rollback(self) -> None:
        # There is no open HTTP transaction to roll back. Failed RPCs roll back in PostgreSQL.
        return None


class _RpcOwnedIdempotencyRepository(IdempotencyRepository):
    """Compatibility port: idempotency is exclusively owned by the transition RPC.

    Returning a cached result here would be unsafe because this narrow port receives
    only the key and cannot verify that a replay request has the same order, target,
    expected version, and actor. The authoritative RPC performs that complete match.
    """

    async def get_result(self, key: str) -> PersistedOrderTransition | None:
        del key
        return None

    async def store_result(self, key: str, result: PersistedOrderTransition) -> None:
        del key, result
        return None
