import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.receipt_verification_service import OrderVerificationSnapshotReader
from app.domain.receipt_verification_context import ReceiptVerificationContext

class SupabaseRpcClientProtocol:
    def rpc(self, function_name: str, params: dict[str, Any]) -> Any: ...

@dataclass(frozen=True, slots=True)
class SupabaseOrderVerificationSnapshotRepository(OrderVerificationSnapshotReader):
    client: SupabaseRpcClientProtocol

    async def get_receipt_verification_context(self, order_id: UUID) -> ReceiptVerificationContext | None:
        params = {"p_order_id": str(order_id)}
        
        # We need an RPC to fetch this, or we can use the postgrest API directly.
        # Since we use RPC for everything else, let's assume we can fetch it via PostgREST client:
        # Actually we can do it with supabase-py postgrest client
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table("orders")
                .select("internal_order_id, public_order_code, network_code, order_financial_snapshots!inner(payment_currency, local_amount, exchange_rate, fee_percent, rounding_policy_version), wallets!inner(address)")
                .eq("internal_order_id", str(order_id))
                .execute()
            )
            data = response.data
            if not data:
                return None
            row = data[0]
            fin = row["order_financial_snapshots"]
            wallet = row["wallets"]
            
            return ReceiptVerificationContext(
                order_id=UUID(row["internal_order_id"]),
                payment_currency=fin["payment_currency"],
                expected_payment_amount=Decimal(str(fin["local_amount"])),
                exchange_rate=Decimal(str(fin["exchange_rate"])) if fin.get("exchange_rate") is not None else None,
                fee_percent=Decimal(str(fin["fee_percent"])),
                rounding_policy_version=fin["rounding_policy_version"],
                network_code=row["network_code"],
                wallet_address=wallet["address"],
                expected_reference=row["public_order_code"]
            )
        except Exception as exc:
            raise RuntimeError("Failed to fetch order verification snapshot") from exc
