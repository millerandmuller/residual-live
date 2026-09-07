"""
residual_live.schemas._types
============================
Shared primitive types used across all domain schemas.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Money — immutable, currency-aware, two-decimal precision
# ---------------------------------------------------------------------------

class Money(BaseModel):
    """
    Represents an exact monetary amount with ISO-4217 currency code.

    All arithmetic is performed in Python ``Decimal`` to avoid float drift in
    royalty calculations where even a fraction of a cent matters legally.
    """

    model_config = {"frozen": True}

    amount: Decimal = Field(
        description="Exact amount, rounded to 2 decimal places.",
        examples=[Decimal("12345.67")],
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        description="ISO-4217 three-letter currency code (e.g. 'USD', 'EUR').",
        examples=["USD"],
    )

    @field_validator("amount", mode="before")
    @classmethod
    def normalise_to_two_decimals(cls, v: Any) -> Decimal:
        d = Decimal(str(v))
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @field_validator("currency", mode="before")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.strip().upper()

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(
                f"Cannot add {self.currency} and {other.currency} without conversion."
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __repr__(self) -> str:
        return f"{self.currency} {self.amount:,.2f}"


# ---------------------------------------------------------------------------
# AuditHash — canonical SHA-256 fingerprint of any serialisable payload
# ---------------------------------------------------------------------------

def compute_sha256(payload: dict[str, Any]) -> str:
    """
    Deterministic SHA-256 over a JSON-serialised dict.

    Keys are sorted and floats/Decimals are converted to strings so the same
    logical data always produces the same hash regardless of insertion order.
    """
    canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Convenience type aliases used in Field annotations
# ---------------------------------------------------------------------------

NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal("0"))]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"))]
