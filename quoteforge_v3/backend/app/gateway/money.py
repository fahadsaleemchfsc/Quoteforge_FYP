"""Money utilities — cents-as-int conversion without float surprises."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENTS_PER_DOLLAR = Decimal("100")


def dollars_to_cents(value: float | int | str | Decimal) -> int:
    """Convert a dollar amount to integer cents.

    Goes through Decimal(str(...)) to avoid float → Decimal(1.1) weirdness.
    Rounds half-up at the 1-cent boundary (standard accounting rounding).
    """
    d = Decimal(str(value)) * CENTS_PER_DOLLAR
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_dollars(cents: int) -> float:
    """Integer cents to a float dollar amount. Safe because 0.01 quantum is
    always representable once you're at 2 decimal places."""
    return float(Decimal(cents) / CENTS_PER_DOLLAR)
