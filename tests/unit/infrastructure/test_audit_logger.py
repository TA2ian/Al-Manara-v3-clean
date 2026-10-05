from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.infrastructure.persistence.audit_logger import AuditPersistenceError, SupabaseAuditLogger


@dataclass
class Response:
    error: object | None = None


class Query:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.inserted: dict | None = None

    def insert(self, values: dict):
        self.inserted = values
        return self

    def execute(self):
        return self.response


class Client:
    def __init__(self, response: Response) -> None:
        self.query = Query(response)
        self.table_name: str | None = None

    def table(self, table_name: str):
        self.table_name = table_name
        return self.query


@pytest.mark.asyncio
async def test_audit_logger_appends_to_canonical_audit_table() -> None:
    client = Client(Response())
    target = uuid4()

    await SupabaseAuditLogger(client).record(
        "wallet_disabled",
        actor_user_id=123,
        target_id=target,
        metadata={"wallet_status": "DISABLED"},
    )

    assert client.table_name == "audit_logs"
    assert client.query.inserted == {
        "actor_telegram_user_id": 123,
        "action": "wallet_disabled",
        "target_type": "wallet",
        "target_id": str(target),
        "metadata": {"wallet_status": "DISABLED"},
    }


@pytest.mark.asyncio
async def test_audit_logger_rejects_invalid_actor() -> None:
    with pytest.raises(ValueError):
        await SupabaseAuditLogger(Client(Response())).record(
            "wallet_disabled",
            actor_user_id=0,
            target_id=uuid4(),
            metadata={},
        )


@pytest.mark.asyncio
async def test_audit_logger_wraps_persistence_errors() -> None:
    client = Client(Response(error={"message": "denied"}))

    with pytest.raises(AuditPersistenceError):
        await SupabaseAuditLogger(client).record(
            "wallet_disabled",
            actor_user_id=123,
            target_id=uuid4(),
            metadata={},
        )
