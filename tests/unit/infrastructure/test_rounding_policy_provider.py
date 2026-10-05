from __future__ import annotations

from typing import Any

import pytest

from app.infrastructure.persistence.quote_support_repository import (
    QuoteSupportPersistenceError,
    SupabaseRoundingPolicyProvider,
)


class Response:
    def __init__(self, data: Any, error: Any = None) -> None:
        self.data = data
        self.error = error


class Query:
    def __init__(self, response: Response) -> None:
        self.response = response

    def execute(self) -> Response:
        return self.response


class Client:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, function_name: str, params: dict[str, Any]) -> Query:
        self.calls.append((function_name, params))
        return Query(self.response)


@pytest.mark.asyncio
async def test_rounding_policy_provider_returns_configured_version() -> None:
    client = Client(Response([{"version": "ROUND_HALF_UP:v2"}]))

    result = await SupabaseRoundingPolicyProvider(client).get_current_version()

    assert result == "ROUND_HALF_UP:v2"
    assert client.calls == [("get_current_rounding_policy", {})]


@pytest.mark.asyncio
async def test_rounding_policy_provider_rejects_missing_or_ambiguous_payload() -> None:
    for payload in ([], [{"version": ""}], [{"version": "a"}, {"version": "b"}]):
        with pytest.raises(QuoteSupportPersistenceError):
            await SupabaseRoundingPolicyProvider(Client(Response(payload))).get_current_version()
