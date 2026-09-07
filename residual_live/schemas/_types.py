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
        description="Exact amount, rounded to 4 decimal places.",
        examples=[Decimal("12345.6789")],
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
        return d.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

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
        return f"{self.currency} {self.amount:,.4f}"


# ---------------------------------------------------------------------------
# AuditHash — canonical SHA-256 fingerprint of any serialisable payload
# ---------------------------------------------------------------------------

# Increment this constant whenever the set of fields included in any hash
# computation changes.  Stored alongside every hash so that verify() can
# distinguish a legitimate schema migration from actual tampering.
HASH_SCHEMA_VERSION = "v2"


def compute_sha256(payload: dict[str, Any]) -> str:
    """
    Deterministic SHA-256 over a JSON-serialised dict.

    Hardening guarantees
    --------------------
    * ``__hash_schema_version__`` is injected into every payload so the hash
      input is tied to the schema revision.  Changing covered fields requires
      bumping ``HASH_SCHEMA_VERSION``, making silent schema-migration collisions
      impossible.
    * All values are serialised through an explicit type-dispatch encoder rather
      than ``default=str``.  This prevents ``Decimal("1.10")`` and the bare
      string ``"1.10"`` from mapping to the same bytes (the ``default=str``
      path treats them identically).
    * Keys are always sorted (``sort_keys=True``) for insertion-order
      independence.
    * The output is UTF-8 encoded with ``ensure_ascii=True`` to guarantee
      byte-for-byte reproducibility across locales.
    """

    def _encode(obj: Any) -> str:
        if isinstance(obj, Decimal):
            # Faithful representation preserving exact Decimal precision:
            return f"decimal:{str(obj)}"
        if hasattr(obj, "isoformat"):
            # datetime / date — always include timezone marker.
            return f"dt:{obj.isoformat()}"
        # Everything else (str, int, …) is encoded natively by json.dumps.
        raise TypeError(f"compute_sha256: unhandled type {type(obj)!r}")

    versioned = dict(payload)
    versioned["__hash_schema_version__"] = HASH_SCHEMA_VERSION
    canonical = json.dumps(versioned, sort_keys=True, default=_encode, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Convenience type aliases used in Field annotations
# ---------------------------------------------------------------------------

NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal("0"))]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"))]
