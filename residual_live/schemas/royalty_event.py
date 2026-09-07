"""
residual_live.schemas.royalty_event  # noqa: D205
====================================
RoyaltyEvent — one streaming-usage event arriving from the Confluent topic
``demo-events``.

Each event represents a single exploitation of a licensed title (e.g. a
broadcast play, an on-demand stream, a theatrical screening) and carries
enough information to apply the matching ContractRule and compute the
resulting payment obligation.

Design notes
------------
* ``event_id`` is the Confluent message key / offset fingerprint.  It MUST be
  unique; the Confluent consumer must reject duplicates (idempotent consumer
  pattern).
* ``occurred_at`` is the wall-clock time the exploitation happened (e.g. when
  the stream started), NOT the Kafka ingestion time.
* ``play_count`` / ``stream_minutes`` are mutually exclusive depending on
  channel: broadcast/theatrical use play_count; svod/avod use stream_minutes.
  A model-level validator enforces this.
* All monetary amounts inside an event are *observed* values from the source
  system (e.g. reported licence fee) — NOT computed royalties.  Royalty
  computation happens in the ADK Schwellenwächter agent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class UsageChannel(str, Enum):
    """Distribution channel of the exploitation event."""
    SVOD = "svod"            # Subscription video on-demand (Netflix-style)
    AVOD = "avod"            # Ad-supported video on-demand (YouTube-style)
    BROADCAST = "broadcast"  # Traditional linear TV
    THEATRICAL = "theatrical"  # Cinema / theatrical release
    TVOD = "tvod"            # Transactional / pay-per-view
    RADIO = "radio"          # Radio / audio broadcast
    PODCAST = "podcast"      # On-demand audio


class RightsTerritory(str, Enum):
    """ISO-3166-1 alpha-2 territory codes relevant for rights clearances."""
    DE = "DE"   # Germany
    AT = "AT"   # Austria
    CH = "CH"   # Switzerland
    US = "US"
    GB = "GB"
    FR = "FR"
    IT = "IT"
    ES = "ES"
    JP = "JP"
    AU = "AU"
    ROW = "ROW"  # Rest of World (catch-all when no single territory applies)


# ---------------------------------------------------------------------------
# RoyaltyEvent
# ---------------------------------------------------------------------------

class RoyaltyEvent(BaseModel):
    """
    A single exploitation event for a licensed media title.

    Produced by source systems (OTT platforms, broadcast schedulers, cinema
    APIs) and published to the Confluent topic ``demo-events``.  The
    Schwellenwächter ADK agent consumes these events and matches them against
    ContractRules to accumulate SettlementNotices.

    Example (SVOD stream)::

        RoyaltyEvent(
            title_id="TITLE-001",
            title_name="The Last Frontier",
            licensee_id="LICENSEE-NF-42",
            licensee_name="StreamCo Europe",
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.DE,
            stream_minutes=Decimal("95.5"),
            licence_fee_reported=Money(amount="0.0", currency="USD"),
        )
    """

    model_config = {
        "frozen": True,
        "populate_by_name": True,
    }

    # --- Identity -----------------------------------------------------------

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique event identifier (UUID v4 or Confluent offset key).",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )

    occurred_at: datetime = Field(
        description=(
            "Wall-clock timestamp of the actual exploitation (not ingestion time). "
            "Must be timezone-aware (UTC preferred)."
        ),
        examples=["2026-09-07T14:32:00Z"],
    )

    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this event was ingested into the pipeline.",
    )

    # --- Title / Rights -----------------------------------------------------

    title_id: str = Field(
        min_length=1,
        max_length=128,
        description="Internal or ISAN title identifier.",
        examples=["TITLE-001", "ISAN 0000-0001-8947-0000-P-0000-0000-Q"],
    )

    title_name: str = Field(
        min_length=1,
        max_length=512,
        description="Human-readable title name for display and audit.",
        examples=["The Last Frontier"],
    )

    contract_id: str = Field(
        description=(
            "References the ContractRule.contract_id whose clauses govern "
            "this event.  Must match an active contract at occurred_at."
        ),
        examples=["CONTRACT-2025-NF-DE-001"],
    )

    # --- Exploitation details ------------------------------------------------

    channel: UsageChannel = Field(
        description="Distribution channel through which the title was exploited.",
    )

    territory: RightsTerritory = Field(
        description="Primary rights territory of the exploitation.",
    )

    # --- Usage metrics — exactly one must be provided per channel -----------

    play_count: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Number of discrete plays/screenings.  Required for BROADCAST, "
            "THEATRICAL, TVOD, RADIO, PODCAST.  Mutually exclusive with "
            "stream_minutes."
        ),
        examples=[1, 12],
    )

    stream_minutes: Optional[Decimal] = Field(
        default=None,
        description=(
            "Total streamed minutes (fractional allowed).  Required for SVOD and "
            "AVOD.  Mutually exclusive with play_count."
        ),
        examples=[Decimal("95.5")],
    )

    audience_size: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Reported audience or unique-viewer count.  Optional but improves "
            "pro-rata calculations where the contract requires it."
        ),
        examples=[42000],
    )

    # --- Financials reported by the licensee --------------------------------

    gross_revenue_reported: Optional[Decimal] = Field(
        default=None,
        description=(
            "Gross revenue reported by the licensee for this event window, in "
            "licence_fee_currency.  Required when the contract uses a "
            "revenue-share basis."
        ),
        examples=[Decimal("125000.00")],
    )

    licence_fee_currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
        description="ISO-4217 currency code for all monetary fields in this event.",
    )

    # --- Source metadata ----------------------------------------------------

    source_system: str = Field(
        default="confluent/demo-events",
        description="Origin system identifier (useful for multi-source pipelines).",
    )

    kafka_offset: Optional[int] = Field(
        default=None,
        ge=0,
        description="Confluent partition offset — set by the consumer, not the producer.",
    )

    kafka_partition: Optional[int] = Field(
        default=None,
        ge=0,
    )

    # --- Validators ---------------------------------------------------------

    @field_validator("occurred_at", mode="before")
    @classmethod
    def require_timezone(cls, v: datetime) -> datetime:
        if isinstance(v, datetime) and v.tzinfo is None:
            raise ValueError(
                "occurred_at must be timezone-aware. "
                "Use datetime(..., tzinfo=timezone.utc) or an ISO-8601 string with offset."
            )
        return v

    @field_validator("licence_fee_currency", mode="before")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_usage_metric(self) -> "RoyaltyEvent":
        """
        Enforce that the correct usage metric is present for the given channel.

        SVOD / AVOD → stream_minutes required, play_count must be None.
        All others   → play_count required, stream_minutes must be None.
        """
        stream_channels = {UsageChannel.SVOD, UsageChannel.AVOD}
        play_channels = {
            UsageChannel.BROADCAST,
            UsageChannel.THEATRICAL,
            UsageChannel.TVOD,
            UsageChannel.RADIO,
            UsageChannel.PODCAST,
        }

        if self.channel in stream_channels:
            if self.stream_minutes is None:
                raise ValueError(
                    f"channel={self.channel.value} requires stream_minutes to be set."
                )
            if self.play_count is not None:
                raise ValueError(
                    f"channel={self.channel.value} must not set play_count "
                    "(use stream_minutes instead)."
                )
            if self.stream_minutes <= 0:
                raise ValueError("stream_minutes must be positive.")

        elif self.channel in play_channels:
            if self.play_count is None:
                raise ValueError(
                    f"channel={self.channel.value} requires play_count to be set."
                )
            if self.stream_minutes is not None:
                raise ValueError(
                    f"channel={self.channel.value} must not set stream_minutes "
                    "(use play_count instead)."
                )

        return self
