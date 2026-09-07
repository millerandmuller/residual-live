"""
residual_live.schemas.contract_rule
=====================================
ContractRule — a single parsed clause from a licence agreement.

A contract is modelled as a *list* of ContractRules.  Each rule maps a
combination of (channel, territory) to a royalty computation method.  The
Klausel-Leser ADK agent reads the raw contract document and emits one
ContractRule per operative clause.

Supported rule types
--------------------
FLAT_FEE_PER_PLAY
    A fixed amount is due per qualifying play/screening.
    ``unit_rate`` is required; basis ignored.

REVENUE_SHARE
    A percentage of the licensee's gross revenue for the period.
    ``rate_percent`` is required; ``minimum_guarantee`` is optional.

MINIMUM_GUARANTEE
    A floor amount that is due regardless of usage.
    ``minimum_guarantee`` required; often combined with REVENUE_SHARE as a
    separate rule (MG + RS are additive, winner takes all, etc.).

PER_STREAM_MINUTE
    A micro-rate per streamed minute (typical for SVOD/AVOD long-tail deals).
    ``unit_rate`` required.

THRESHOLD_TRIGGER
    When cumulative usage (in ``threshold_basis`` units) crosses
    ``threshold_value``, the rule fires and ``unit_rate`` is applied to the
    entire accumulated amount.  This is the rule type that drives the Hero
    Moment in the demo.

PRO_RATA
    Usage-proportional share of a fixed licence pool.  Pool size is in
    ``pool_total``; audience size is the denominator.

Design notes
------------
* ``effective_from`` / ``effective_until`` guard temporal applicability — the
  Schwellenwächter only applies a rule when
  ``effective_from <= event.occurred_at < effective_until``.
* ``clause_reference`` carries the original contract clause number (e.g.
  "§ 4.2 (b)") — shown verbatim in the SettlementNotice for transparency.
* A ContractRule is intentionally *immutable* (frozen model).  Contract
  amendments produce new rules with updated validity windows, not mutations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from ._types import Money
from .royalty_event import UsageChannel, RightsTerritory


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RuleType(str, Enum):
    """Royalty computation method encoded in this clause."""
    FLAT_FEE_PER_PLAY = "flat_fee_per_play"
    REVENUE_SHARE = "revenue_share"
    MINIMUM_GUARANTEE = "minimum_guarantee"
    PER_STREAM_MINUTE = "per_stream_minute"
    THRESHOLD_TRIGGER = "threshold_trigger"
    PRO_RATA = "pro_rata"


class ThresholdBasis(str, Enum):
    """The unit against which the threshold is measured (THRESHOLD_TRIGGER only)."""
    PLAY_COUNT = "play_count"
    STREAM_MINUTES = "stream_minutes"
    GROSS_REVENUE = "gross_revenue"
    AUDIENCE_SIZE = "audience_size"


class ThresholdOperator(str, Enum):
    """Comparison operator for the threshold check."""
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="


# ---------------------------------------------------------------------------
# ContractRule
# ---------------------------------------------------------------------------

class ContractRule(BaseModel):
    """
    A single operative royalty clause parsed from a licence agreement.

    Example (threshold-trigger rule that fires the Hero Moment)::

        ContractRule(
            rule_id="RULE-NF-DE-2025-001",
            contract_id="CONTRACT-2025-NF-DE-001",
            clause_reference="§ 4.2 (b)",
            rule_type=RuleType.THRESHOLD_TRIGGER,
            channels=[UsageChannel.SVOD],
            territories=[RightsTerritory.DE],
            threshold_basis=ThresholdBasis.STREAM_MINUTES,
            threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
            threshold_value=Decimal("100000"),
            unit_rate=Money(amount="0.0012", currency="USD"),
            effective_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
    """

    model_config = {
        "frozen": True,
        "populate_by_name": True,
    }

    # --- Identity -----------------------------------------------------------

    rule_id: str = Field(
        description="Unique identifier for this rule clause.",
        examples=["RULE-NF-DE-2025-001"],
    )

    contract_id: str = Field(
        description=(
            "Parent contract this rule belongs to.  Must match "
            "RoyaltyEvent.contract_id when applying."
        ),
        examples=["CONTRACT-2025-NF-DE-001"],
    )

    clause_reference: str = Field(
        description=(
            "Human-readable clause reference from the source document "
            "(shown verbatim in the SettlementNotice audit trail)."
        ),
        examples=["§ 4.2 (b)", "Section 7.1", "Annex B, Row 3"],
    )

    rule_type: RuleType = Field(
        description="Royalty computation method for this clause.",
    )

    # --- Scope: channels and territories ------------------------------------

    channels: list[UsageChannel] = Field(
        min_length=1,
        description=(
            "List of UsageChannels this rule applies to.  "
            "An event's channel must appear in this list."
        ),
        examples=[["svod", "avod"]],
    )

    territories: list[RightsTerritory] = Field(
        min_length=1,
        description=(
            "List of RightsTerritory values this rule applies to.  "
            "ROW acts as a catch-all when the event territory is not listed "
            "in any more-specific rule."
        ),
        examples=[["DE", "AT", "CH"]],
    )

    # --- Temporal applicability ---------------------------------------------

    effective_from: datetime = Field(
        description=(
            "Inclusive start of the rule's validity window (timezone-aware). "
            "Events with occurred_at < effective_from are not governed by this rule."
        ),
    )

    effective_until: Optional[datetime] = Field(
        default=None,
        description=(
            "Exclusive end of the validity window.  None = open-ended (rule "
            "remains active until superseded by a new amendment)."
        ),
    )

    # --- Rate parameters — which fields are required depends on rule_type ---

    unit_rate: Optional[Money] = Field(
        default=None,
        description=(
            "Per-unit rate.  Required for FLAT_FEE_PER_PLAY, "
            "PER_STREAM_MINUTE, and THRESHOLD_TRIGGER."
        ),
    )

    rate_percent: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
        description=(
            "Revenue-share percentage (0–100).  "
            "Required for REVENUE_SHARE."
        ),
        examples=[Decimal("12.5")],
    )

    minimum_guarantee: Optional[Money] = Field(
        default=None,
        description=(
            "Floor amount guaranteed regardless of usage.  "
            "Required for MINIMUM_GUARANTEE; optional additive floor for "
            "REVENUE_SHARE."
        ),
    )

    pool_total: Optional[Money] = Field(
        default=None,
        description=(
            "Total pool to be distributed pro-rata.  "
            "Required for PRO_RATA."
        ),
    )

    # --- Threshold parameters (THRESHOLD_TRIGGER only) ---------------------

    threshold_basis: Optional[ThresholdBasis] = Field(
        default=None,
        description="Unit that accumulates toward the threshold.  Required for THRESHOLD_TRIGGER.",
    )

    threshold_operator: Optional[ThresholdOperator] = Field(
        default=None,
        description="Comparison direction.  Required for THRESHOLD_TRIGGER.",
    )

    threshold_value: Optional[Decimal] = Field(
        default=None,
        gt=Decimal("0"),
        description=(
            "The accumulated value that triggers rule execution.  "
            "Required for THRESHOLD_TRIGGER."
        ),
        examples=[Decimal("100000")],
    )

    apply_rate_to_full_accumulation: bool = Field(
        default=True,
        description=(
            "THRESHOLD_TRIGGER only.  When True, unit_rate is applied to the "
            "entire accumulated value once the threshold is crossed "
            "(retrospective billing).  When False, only the excess above the "
            "threshold is rated."
        ),
    )

    # --- Optional override label (for display) ------------------------------

    display_label: Optional[str] = Field(
        default=None,
        description="Short human-readable label shown in the UI settlement table.",
        examples=["SVOD DACH Threshold Trigger ≥ 100k min"],
    )

    # --- Validators ---------------------------------------------------------

    @model_validator(mode="after")
    def validate_rate_fields_for_rule_type(self) -> "ContractRule":
        rt = self.rule_type

        if rt in (
            RuleType.FLAT_FEE_PER_PLAY,
            RuleType.PER_STREAM_MINUTE,
            RuleType.THRESHOLD_TRIGGER,
        ):
            if self.unit_rate is None:
                raise ValueError(
                    f"rule_type={rt.value} requires unit_rate to be set."
                )

        if rt == RuleType.REVENUE_SHARE:
            if self.rate_percent is None:
                raise ValueError("rule_type=revenue_share requires rate_percent.")

        if rt == RuleType.MINIMUM_GUARANTEE:
            if self.minimum_guarantee is None:
                raise ValueError(
                    "rule_type=minimum_guarantee requires minimum_guarantee to be set."
                )

        if rt == RuleType.PRO_RATA:
            if self.pool_total is None:
                raise ValueError("rule_type=pro_rata requires pool_total to be set.")

        if rt == RuleType.THRESHOLD_TRIGGER:
            missing = [
                name
                for name, val in (
                    ("threshold_basis", self.threshold_basis),
                    ("threshold_operator", self.threshold_operator),
                    ("threshold_value", self.threshold_value),
                )
                if val is None
            ]
            if missing:
                raise ValueError(
                    f"rule_type=threshold_trigger requires: {', '.join(missing)}."
                )

        return self

    @model_validator(mode="after")
    def validate_temporal_window(self) -> "ContractRule":
        if self.effective_until is not None:
            if self.effective_until <= self.effective_from:
                raise ValueError(
                    "effective_until must be strictly after effective_from."
                )
        return self

    # --- Domain helpers -----------------------------------------------------

    def is_active_at(self, moment: datetime) -> bool:
        """Return True if this rule governs events occurring at *moment*."""
        if moment < self.effective_from:
            return False
        if self.effective_until is not None and moment >= self.effective_until:
            return False
        return True

    def matches_event(self, event: "RoyaltyEvent") -> bool:  # type: ignore[name-defined]
        """
        Return True if this rule is applicable to *event*.

        Checks channel scope, territory scope, and temporal validity.
        Does NOT perform the monetary calculation — that is the agent's job.
        """
        if not self.is_active_at(event.occurred_at):
            return False
        if event.channel not in self.channels:
            return False
        # ROW is a catch-all: a rule scoped to ROW matches any territory
        territory_match = (
            event.territory in self.territories
            or RightsTerritory.ROW in self.territories
        )
        return territory_match
