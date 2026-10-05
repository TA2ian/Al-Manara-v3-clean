from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


USD_QUANTUM = Decimal("0.01")
NEW_SYP_QUANTUM = Decimal("0.01")
USDT_QUANTUM = Decimal("0.001")
RATE_QUANTUM = Decimal("0.001")


class MoneyError(ValueError):
    """Raised when a monetary value violates the domain precision contract."""


def quantize_half_up(value: Decimal, quantum: Decimal) -> Decimal:
    if not value.is_finite():
        raise MoneyError("value must be finite")
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class OrderFinancials:
    requested_amount: Decimal
    fee_percent: Decimal
    fee_amount: Decimal
    net_usdt_amount: Decimal
    payment_currency: str
    exchange_rate: Decimal | None
    local_amount: Decimal
    rounding_policy_version: str
    network_fixed_fee_usdt: Decimal = Decimal("0")
    total_fee_usdt: Decimal = Decimal("0")

    @classmethod
    def calculate(
        cls,
        requested_amount: Decimal,
        fee_percent: Decimal,
        payment_currency: str,
        exchange_rate: Decimal | None,
        rounding_policy_version: str,
        network_fixed_fee_usdt: Decimal = Decimal("0"),
    ) -> OrderFinancials:
        requested = quantize_half_up(requested_amount, USDT_QUANTUM)
        fee_rate = fee_percent / Decimal("100")
        if requested <= 0:
            raise MoneyError("requested_amount must be positive")
        if fee_percent < 0 or fee_percent >= 100:
            raise MoneyError("fee_percent must be in [0, 100)")

        fee = quantize_half_up(requested * fee_rate, USDT_QUANTUM)
        fixed_network_fee = quantize_half_up(network_fixed_fee_usdt, USDT_QUANTUM)
        if fixed_network_fee < 0:
            raise MoneyError("network_fixed_fee_usdt must be non-negative")
        total_fee = quantize_half_up(fee + fixed_network_fee, USDT_QUANTUM)
        net = quantize_half_up(requested - total_fee, USDT_QUANTUM)
        if net <= 0:
            raise MoneyError("net_usdt_amount must remain positive")

        if payment_currency == "USD":
            if exchange_rate is not None:
                raise MoneyError("USD payment must not use an exchange rate")
            local = quantize_half_up(requested, USD_QUANTUM)
        elif payment_currency == "NEW.SYP":
            if exchange_rate is None or exchange_rate <= 0:
                raise MoneyError("NEW.SYP payment requires a positive exchange rate")
            rate = quantize_half_up(exchange_rate, RATE_QUANTUM)
            local = quantize_half_up(requested * rate, NEW_SYP_QUANTUM)
            exchange_rate = rate
        else:
            raise MoneyError(f"unsupported payment currency: {payment_currency}")

        return cls(
            requested_amount=requested,
            fee_percent=fee_percent,
            fee_amount=fee,
            net_usdt_amount=net,
            payment_currency=payment_currency,
            exchange_rate=exchange_rate,
            local_amount=local,
            rounding_policy_version=rounding_policy_version,
            network_fixed_fee_usdt=fixed_network_fee,
            total_fee_usdt=total_fee,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "requested_amount": str(self.requested_amount),
            "fee_percent": str(self.fee_percent),
            "fee_amount": str(self.fee_amount),
            "net_usdt_amount": str(self.net_usdt_amount),
            "payment_currency": self.payment_currency,
            "exchange_rate": str(self.exchange_rate) if self.exchange_rate is not None else "",
            "local_amount": str(self.local_amount),
            "rounding_policy_version": self.rounding_policy_version,
            "network_fixed_fee_usdt": str(self.network_fixed_fee_usdt),
            "total_fee_usdt": str(self.total_fee_usdt),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> OrderFinancials:
        return cls(
            requested_amount=Decimal(data["requested_amount"]),
            fee_percent=Decimal(data["fee_percent"]),
            fee_amount=Decimal(data["fee_amount"]),
            net_usdt_amount=Decimal(data["net_usdt_amount"]),
            payment_currency=data["payment_currency"],
            exchange_rate=Decimal(data["exchange_rate"]) if data.get("exchange_rate") else None,
            local_amount=Decimal(data["local_amount"]),
            rounding_policy_version=data["rounding_policy_version"],
            network_fixed_fee_usdt=Decimal(data.get("network_fixed_fee_usdt", "0")),
            total_fee_usdt=Decimal(data.get("total_fee_usdt", data["fee_amount"])),
        )
