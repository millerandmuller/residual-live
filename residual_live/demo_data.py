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

TITLE_2_ID = "TITLE-NEON-2026"
TITLE_2_NAME = "Neon Horizon"
TITLE_2_CONTRACT_ID = "AGR-DACH-AVOD-2026-042"

TITLE_3_ID = "TITLE-QUANTUM-2026"
TITLE_3_NAME = "Quantum Fallback"
TITLE_3_CONTRACT_ID = "AGR-BROADCAST-GLOBAL-2026-019"

TITLES = {
    SAMPLE_TITLE_ID: {
        "title_id": SAMPLE_TITLE_ID,
        "title_name": SAMPLE_TITLE_NAME,
        "contract_id": SAMPLE_CONTRACT_ID,
        "licensor": "Sovereign Media Rights LLC",
        "licensee": "Global Cinema Distribution Corp",
        "primary": True,
        "color": "indigo",
    },
    TITLE_2_ID: {
        "title_id": TITLE_2_ID,
        "title_name": TITLE_2_NAME,
        "contract_id": TITLE_2_CONTRACT_ID,
        "licensor": "Neon Pictures GmbH",
        "licensee": "StreamDE Verwertungs GmbH",
        "primary": False,
        "color": "emerald",
    },
    TITLE_3_ID: {
        "title_id": TITLE_3_ID,
        "title_name": TITLE_3_NAME,
        "contract_id": TITLE_3_CONTRACT_ID,
        "licensor": "Quantum Film Partners Ltd",
        "licensee": "Worldwide Broadcast Holdings Inc",
        "primary": False,
        "color": "amber",
    },
}


def create_curated_demo_stream() -> List[RoyaltyEvent]:
    """
    Generate a curated multi-title streaming sequence with 3 titles running in parallel.
    First 6 events drive the Echoes of Eternity Hero Moment (crossing 5M mins),
    followed immediately by the multi-title scaling beat with Neon Horizon (DACH AVOD/SVOD)
    and Quantum Fallback (Worldwide Broadcast).
    """
    now = datetime.now(timezone.utc)
    events = []

    # 1. Baseline historical chunk for Echoes (4,200,000 minutes)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-001-BASE",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("4200000"),
            occurred_at=now - timedelta(hours=4),
            licence_fee_currency="USD",
        )
    )

    # 2. Echoes steady accrual (+250,000 -> 4,450,000 min)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-002-STREAM",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("250000"),
            occurred_at=now - timedelta(hours=3),
            licence_fee_currency="USD",
        )
    )

    # 3. Echoes steady accrual (+180,000 -> 4,630,000 min)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-003-STREAM",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("180000"),
            occurred_at=now - timedelta(hours=2, minutes=30),
            licence_fee_currency="USD",
        )
    )

    # 4. Echoes steady accrual (+150,000 -> 4,780,000 min)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-004-STREAM",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("150000"),
            occurred_at=now - timedelta(hours=2),
            licence_fee_currency="USD",
        )
    )

    # 5. Echoes approaching threshold (+140,000 -> 4,920,000 min)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-005-STREAM",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("140000"),
            occurred_at=now - timedelta(hours=1),
            licence_fee_currency="USD",
        )
    )

    # 6. THE TIPPING POINT (HERO MOMENT): +120,000 -> 5,040,000 min (crosses 5M threshold!)
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

    # 7. MULTI-TITLE SCALING: Neon Horizon AVOD stream in DACH (300,000 minutes)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-007-NEON-AVOD",
            title_id=TITLE_2_ID,
            title_name=TITLE_2_NAME,
            contract_id=TITLE_2_CONTRACT_ID,
            channel=UsageChannel.AVOD,
            territory=RightsTerritory.DE,
            stream_minutes=Decimal("300000"),
            gross_revenue_reported=Decimal("18500.00"),
            occurred_at=now - timedelta(minutes=12),
            licence_fee_currency="EUR",
        )
    )

    # 8. MULTI-TITLE SCALING: Quantum Fallback Global Broadcast (50 plays)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-008-QFB-BCAST",
            title_id=TITLE_3_ID,
            title_name=TITLE_3_NAME,
            contract_id=TITLE_3_CONTRACT_ID,
            channel=UsageChannel.BROADCAST,
            territory=RightsTerritory.ROW,
            play_count=50,
            occurred_at=now - timedelta(minutes=10),
            licence_fee_currency="USD",
        )
    )

    # 9. MULTI-TITLE SCALING: Neon Horizon SVOD stream in AT (120,000 minutes)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-009-NEON-SVOD",
            title_id=TITLE_2_ID,
            title_name=TITLE_2_NAME,
            contract_id=TITLE_2_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.AT,
            stream_minutes=Decimal("120000"),
            gross_revenue_reported=Decimal("9200.00"),
            occurred_at=now - timedelta(minutes=7),
            licence_fee_currency="EUR",
        )
    )

    # 10. MULTI-TITLE SCALING: Quantum Fallback Broadcast (+30 plays)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-010-QFB-BCAST",
            title_id=TITLE_3_ID,
            title_name=TITLE_3_NAME,
            contract_id=TITLE_3_CONTRACT_ID,
            channel=UsageChannel.BROADCAST,
            territory=RightsTerritory.ROW,
            play_count=30,
            occurred_at=now - timedelta(minutes=4),
            licence_fee_currency="USD",
        )
    )

    # 11. Post-threshold continuation on Echoes (+85,000 -> 5,125,000 min)
    events.append(
        RoyaltyEvent(
            event_id="EV-DEMO-011-POST-TRIGGER",
            title_id=SAMPLE_TITLE_ID,
            title_name=SAMPLE_TITLE_NAME,
            contract_id=SAMPLE_CONTRACT_ID,
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("85000"),
            occurred_at=now - timedelta(minutes=1),
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

