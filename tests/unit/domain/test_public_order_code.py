import re

from app.domain.public_order_code import generate_public_order_code


def test_public_order_code_has_expected_opaque_format() -> None:
    code = generate_public_order_code()
    assert re.fullmatch(r"ORD-[A-Z0-9]{10}", code)


def test_public_order_codes_are_not_deterministic_or_sequential() -> None:
    codes = {generate_public_order_code() for _ in range(100)}
    assert len(codes) == 100
