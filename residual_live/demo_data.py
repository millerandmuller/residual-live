"""
residual_live.demo_data
=======================
Curated demonstration event generator for Residual Live.
Provides a deterministic sequence of events designed to drive the 3-minute demo video:
Cold Open -> Accrual -> Tipping Point (Hero Moment at 5M mins) -> Settlement Generation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from .schemas import RightsTerritory, RoyaltyEvent, UsageChannel

SAMPLE_TITLE_ID = "TITLE-ECHOES-2026"
SAMPLE_TITLE_NAME = "Echoes of Eternity"
SAMPLE_CONTRACT_ID = "AGR-SAG-DGA-2026-088"


def create_curated_demo_stream() -> List[RoyaltyEvent]:
    """Generate a curated list of events designed to tip the 5,000,000 minute threshold."""
    now = datetime.now(timezone.utc)
    events = []

    # 1. Baseline historical chunk (4,200,000 minutes)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-001-BASE",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("4200000"),
            occurred_at=now - timedelta(hours=3),
            licence_fee_currency="USD",
        )
    )

    # 2. Steady streaming accrual leading up to threshold
    increments = [
        (Decimal("250000"), timedelta(hours=2, minutes=30)),
        (Decimal("180000"), timedelta(hours=2)),
        (Decimal("150000"), timedelta(hours=1, minutes=30)),
        (Decimal("140000"), timedelta(hours=1)),
    ]
    # At this point: 4,200,000 + 250,000 + 180,000 + 150,000 + 140,000 = 4,920,000 minutes!

    for idx, (mins, delta) in enumerate(increments, start=2):
        events.append(
            RoyaltyEvent(
                event_id=f"EV-DEMO-{idx:03d}-STREAM",
                title_id=SAMPLE_TITLE_ID,
                title_name=SAMPLE_TITLE_NAME,
                contract_id=SAMPLE_CONTRACT_ID,
                channel=UsageChannel.SVOD,
                territory=RightsTerritory.US,
                stream_minutes=mins,
                occurred_at=now - delta,
                licence_fee_currency="USD",
            )
        )

    # 3. The Tipping Point Event (120,000 minutes -> crosses 5,000,000 -> 5,040,000 minutes!)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-006-HERO-BREACH",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("120000"),
            occurred_at=now - timedelta(minutes=15),
            licence_fee_currency="USD",
        )
    )

    # 4. Post-threshold continuation
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-007-POST-TRIGGER",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("85000"),
            occurred_at=now - timedelta(minutes=5),
            licence_fee_currency="USD",
        )
    )

    return events


SAMPLE_SAG_AFTRA_AGREEMENT = """
SAG-AFTRA STANDARD HIGH-BUDGET SVOD RESIDUALS SCHEDULE (2026 EXHIBIT A)
Master License Contract: AGR-SAG-DGA-2026-088
Covered Title Property: "Echoes of Eternity"
Licensor Entity: Sovereign Media Rights LLC
Licensee Distributor: Global Cinema Distribution Corp
Territory: United States & Worldwide Streaming Rights
Governing Guild: SAG-AFTRA

SECTION 4. STREAMING EXPLOITATION & RESIDUAL ACCRUAL SCHEDULE
4.1 Base SVOD Stream Rate:
For all subscriber video-on-demand (SVOD) streaming exploitation within the United States, Licensee shall pay to Licensor a base residual rate of USD 0.0015 per subscriber stream minute ($0.0015/stream_minute) accrued continuously from the first minute of exhibition.

4.2 High-Volume Exhibition Milestone Escalator:
In the event that aggregate streaming exhibition of the Title exceeds 5,000,000 subscriber stream minutes across authorized platforms during any single accounting cycle, Licensee shall immediately disburse to Licensor a fixed milestone bonus of USD 25,000.00. Notice of threshold attainment and settlement disbursement shall be rendered in real-time.
"""

