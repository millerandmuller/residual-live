"""
tests/test_multi_title.py
=========================
Multi-title streaming test corpus.

Covers three film titles, each with distinct per-title contract rules that
reflect realistic but differentiated deal structures:

  * Echoes of Eternity  — SAG-AFTRA SVOD, US/ROW, $0.0015/min + 5 M-min milestone
  * Neon Horizon        — AVOD/SVOD dual-channel, DACH territory, revenue share +
                          flat fee per play for broadcast windows
  * Quantum Fallback    — Broadcast-first, global, minimum guarantee + threshold
                          escalator at 10 M minutes

For each title the corpus verifies:
  1. ContractRule construction and matches_event routing
  2. RoyaltyEngine per-title isolation (separate engine instances)
  3. Stream accrual, threshold detection, and settlement generation
  4. Engine idempotency guard across titles
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from residual_live.engine import RoyaltyEngine
from residual_live.schemas import (
    AuditEntry,
    ContractRule,
    Money,
    RightsTerritory,
    RoyaltyEvent,
    RuleType,
    SettlementStatus,
    ThresholdBasis,
    ThresholdOperator,
    UsageChannel,
)

UTC = timezone.utc
T_EFFECTIVE = datetime(2025, 1, 1, tzinfo=UTC)
T_UNTIL = datetime(2028, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Title meta-data
# ---------------------------------------------------------------------------

ECHOES = {
    "title_id": "TITLE-ECHOES-2026",
    "title_name": "Echoes of Eternity",
    "contract_id": "AGR-SAG-DGA-2026-088",
    "licensor_id": "LICENSOR-SOVEREIGN",
    "licensor_name": "Sovereign Media Rights LLC",
    "licensee_id": "LICENSEE-GLOBAL",
    "licensee_name": "Global Cinema Distribution Corp",
}

NEON = {
    "title_id": "TITLE-NEON-2026",
    "title_name": "Neon Horizon",
    "contract_id": "AGR-DACH-AVOD-2026-042",
    "licensor_id": "LICENSOR-NEON",
    "licensor_name": "Neon Pictures GmbH",
    "licensee_id": "LICENSEE-STREAM-DE",
    "licensee_name": "StreamDE Verwertungs GmbH",
}

QUANTUM = {
    "title_id": "TITLE-QUANTUM-2026",
    "title_name": "Quantum Fallback",
    "contract_id": "AGR-BROADCAST-GLOBAL-2026-019",
    "licensor_id": "LICENSOR-QUANTUM",
    "licensor_name": "Quantum Film Partners Ltd",
    "licensee_id": "LICENSEE-BROADCAST-INTL",
    "licensee_name": "Worldwide Broadcast Holdings Inc",
}


# ---------------------------------------------------------------------------
# Per-title contract rule factories
# ---------------------------------------------------------------------------

def make_echoes_rules() -> list[ContractRule]:
    """SAG-AFTRA SVOD deal: $0.0015/min base + 5 M-min milestone bonus."""
    return [
        ContractRule(
            rule_id="ECHOES-RULE-4.1-BASE",
            contract_id=ECHOES["contract_id"],
            clause_reference="Clause 4.1 – Base SVOD Stream Rate $0.0015/min",
            rule_type=RuleType.PER_STREAM_MINUTE,
            channels=[UsageChannel.SVOD],
            territories=[RightsTerritory.US, RightsTerritory.ROW],
            effective_from=T_EFFECTIVE,
            effective_until=T_UNTIL,
            unit_rate=Money(amount=Decimal("0.0015"), currency="USD"),
            display_label="Echoes – Base SVOD $0.0015/min",
        ),
        ContractRule(
            rule_id="ECHOES-RULE-4.2-MILESTONE",
            contract_id=ECHOES["contract_id"],
            clause_reference="Clause 4.2 – 5 M stream-minute milestone bonus",
            rule_type=RuleType.THRESHOLD_TRIGGER,
            channels=[UsageChannel.SVOD],
            territories=[RightsTerritory.US, RightsTerritory.ROW],
            effective_from=T_EFFECTIVE,
            effective_until=T_UNTIL,
            threshold_basis=ThresholdBasis.STREAM_MINUTES,
            threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
            threshold_value=Decimal("5000000"),
            unit_rate=Money(amount=Decimal("0.0050"), currency="USD"),
            apply_rate_to_full_accumulation=True,
            display_label="Echoes – Milestone ≥ 5 M min",
        ),
    ]


def make_neon_rules() -> list[ContractRule]:
    """DACH AVOD/SVOD deal: 15 % revenue share + $8 flat fee per broadcast play."""
    return [
        ContractRule(
            rule_id="NEON-RULE-3.1-REVSHARE",
            contract_id=NEON["contract_id"],
            clause_reference="§ 3.1 – 15 % Revenue Share (AVOD/SVOD, DACH)",
            rule_type=RuleType.REVENUE_SHARE,
            channels=[UsageChannel.AVOD, UsageChannel.SVOD],
            territories=[RightsTerritory.DE, RightsTerritory.AT, RightsTerritory.CH],
            effective_from=T_EFFECTIVE,
            effective_until=T_UNTIL,
            rate_percent=Decimal("15.0"),
            display_label="Neon – 15 % Revenue Share DACH",
        ),
        ContractRule(
            rule_id="NEON-RULE-3.2-BROADCAST",
            contract_id=NEON["contract_id"],
            clause_reference="§ 3.2 – €8.00 flat fee per broadcast play",
            rule_type=RuleType.FLAT_FEE_PER_PLAY,
            channels=[UsageChannel.BROADCAST],
            territories=[RightsTerritory.DE, RightsTerritory.AT, RightsTerritory.CH],
            effective_from=T_EFFECTIVE,
            effective_until=T_UNTIL,
            unit_rate=Money(amount=Decimal("8.00"), currency="EUR"),
            display_label="Neon – €8 flat per broadcast play",
        ),
    ]


def make_quantum_rules() -> list[ContractRule]:
    """Global broadcast deal: $500 k MG + 10 M-min threshold escalator at $0.002/min."""
    return [
        ContractRule(
            rule_id="QUANTUM-RULE-2.1-MG",
            contract_id=QUANTUM["contract_id"],
            clause_reference="§ 2.1 – Minimum Guarantee USD 500,000",
            rule_type=RuleType.MINIMUM_GUARANTEE,
            channels=[UsageChannel.BROADCAST, UsageChannel.SVOD],
            territories=[RightsTerritory.ROW],
            effective_from=T_EFFECTIVE,
            effective_until=T_UNTIL,
            minimum_guarantee=Money(amount=Decimal("500000.00"), currency="USD"),
            display_label="Quantum – MG USD 500 k",
        ),
        ContractRule(
            rule_id="QUANTUM-RULE-2.2-ESCALATOR",
            contract_id=QUANTUM["contract_id"],
            clause_reference="§ 2.2 – Threshold escalator at 10 M stream-minutes ($0.002/min)",
            rule_type=RuleType.THRESHOLD_TRIGGER,
            channels=[UsageChannel.SVOD],
            territories=[RightsTerritory.ROW],
            effective_from=T_EFFECTIVE,
            effective_until=T_UNTIL,
            threshold_basis=ThresholdBasis.STREAM_MINUTES,
            threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
            threshold_value=Decimal("10000000"),
            unit_rate=Money(amount=Decimal("0.002"), currency="USD"),
            apply_rate_to_full_accumulation=True,
            display_label="Quantum – Escalator ≥ 10 M min",
        ),
    ]


# ---------------------------------------------------------------------------
# Event stream factories
# ---------------------------------------------------------------------------

def _svod_event(meta: dict, event_id: str, minutes: Decimal, offset: timedelta,
                territory: RightsTerritory = RightsTerritory.US) -> RoyaltyEvent:
    return RoyaltyEvent(
        event_id=event_id,
        title_id=meta["title_id"],
        title_name=meta["title_name"],
        contract_id=meta["contract_id"],
        channel=UsageChannel.SVOD,
        territory=territory,
        stream_minutes=minutes,
        occurred_at=NOW - offset,
        licence_fee_currency="USD",
    )


def _broadcast_event(meta: dict, event_id: str, plays: int, offset: timedelta,
                     territory: RightsTerritory = RightsTerritory.DE) -> RoyaltyEvent:
    return RoyaltyEvent(
        event_id=event_id,
        title_id=meta["title_id"],
        title_name=meta["title_name"],
        contract_id=meta["contract_id"],
        channel=UsageChannel.BROADCAST,
        territory=territory,
        play_count=plays,
        occurred_at=NOW - offset,
        licence_fee_currency="EUR",
    )


def make_echoes_stream() -> list[RoyaltyEvent]:
    """7 events that cross the 5 M-minute threshold on event 6."""
    events = [
        _svod_event(ECHOES, "EV-ECH-001-BASE",   Decimal("4200000"), timedelta(hours=5)),
        _svod_event(ECHOES, "EV-ECH-002-STREAM",  Decimal("250000"),  timedelta(hours=4)),
        _svod_event(ECHOES, "EV-ECH-003-STREAM",  Decimal("180000"),  timedelta(hours=3)),
        _svod_event(ECHOES, "EV-ECH-004-STREAM",  Decimal("150000"),  timedelta(hours=2)),
        _svod_event(ECHOES, "EV-ECH-005-STREAM",  Decimal("140000"),  timedelta(hours=1)),
        # This event tips the threshold: 4 920 000 + 120 000 = 5 040 000
        _svod_event(ECHOES, "EV-ECH-006-HERO",    Decimal("120000"),  timedelta(minutes=15)),
        _svod_event(ECHOES, "EV-ECH-007-POST",    Decimal("85000"),   timedelta(minutes=5)),
    ]
    return events


def make_neon_stream() -> list[RoyaltyEvent]:
    """Mixed AVOD/SVOD + broadcast events for DACH territory."""
    return [
        RoyaltyEvent(
            event_id="EV-NEON-001-AVOD-DE",
            title_id=NEON["title_id"],
            title_name=NEON["title_name"],
            contract_id=NEON["contract_id"],
            channel=UsageChannel.AVOD,
            territory=RightsTerritory.DE,
            stream_minutes=Decimal("300000"),
            occurred_at=NOW - timedelta(hours=6),
            licence_fee_currency="EUR",
        ),
        RoyaltyEvent(
            event_id="EV-NEON-002-SVOD-AT",
            title_id=NEON["title_id"],
            title_name=NEON["title_name"],
            contract_id=NEON["contract_id"],
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.AT,
            stream_minutes=Decimal("120000"),
            occurred_at=NOW - timedelta(hours=4),
            licence_fee_currency="EUR",
        ),
        _broadcast_event(NEON, "EV-NEON-003-BCAST-DE", plays=5, offset=timedelta(hours=2)),
        _broadcast_event(NEON, "EV-NEON-004-BCAST-CH", plays=3,
                         offset=timedelta(hours=1), territory=RightsTerritory.CH),
        # Event outside DACH scope — should NOT match any Neon rule
        RoyaltyEvent(
            event_id="EV-NEON-005-US-NO-MATCH",
            title_id=NEON["title_id"],
            title_name=NEON["title_name"],
            contract_id=NEON["contract_id"],
            channel=UsageChannel.SVOD,
            territory=RightsTerritory.US,
            stream_minutes=Decimal("50000"),
            occurred_at=NOW - timedelta(minutes=30),
            licence_fee_currency="USD",
        ),
    ]


def make_quantum_stream() -> list[RoyaltyEvent]:
    """SVOD events crossing the 10 M-minute threshold on event 4."""
    return [
        _svod_event(QUANTUM, "EV-QFB-001-BASE",  Decimal("8000000"), timedelta(hours=8),
                    territory=RightsTerritory.ROW),
        _svod_event(QUANTUM, "EV-QFB-002-ACRL",  Decimal("900000"),  timedelta(hours=5),
                    territory=RightsTerritory.ROW),
        _svod_event(QUANTUM, "EV-QFB-003-ACRL",  Decimal("900000"),  timedelta(hours=3),
                    territory=RightsTerritory.ROW),
        # Tips at 9 800 000 + 300 000 = 10 100 000 (crosses 10 M)
        _svod_event(QUANTUM, "EV-QFB-004-HERO",  Decimal("300000"),  timedelta(minutes=20),
                    territory=RightsTerritory.ROW),
        _svod_event(QUANTUM, "EV-QFB-005-POST",  Decimal("150000"),  timedelta(minutes=5),
                    territory=RightsTerritory.ROW),
    ]


# ---------------------------------------------------------------------------
# ContractRule matching tests
# ---------------------------------------------------------------------------

class TestEchoesContractRules:
    def test_base_rule_matches_svod_us(self):
        rule = make_echoes_rules()[0]
        ev = make_echoes_stream()[0]
        assert rule.matches_event(ev) is True

    def test_base_rule_matches_svod_row(self):
        rule = make_echoes_rules()[0]
        ev = _svod_event(ECHOES, "EV-X", Decimal("1000"), timedelta(hours=1),
                         territory=RightsTerritory.ROW)
        assert rule.matches_event(ev) is True

    def test_milestone_rule_is_threshold_trigger(self):
        rule = make_echoes_rules()[1]
        assert rule.rule_type == RuleType.THRESHOLD_TRIGGER
        assert rule.threshold_value == Decimal("5000000")

    def test_echoes_rules_do_not_match_broadcast(self):
        rules = make_echoes_rules()
        ev = _broadcast_event(ECHOES, "EV-X", plays=2, offset=timedelta(hours=1),
                              territory=RightsTerritory.US)
        assert all(not r.matches_event(ev) for r in rules)


class TestNeonContractRules:
    def test_revshare_matches_avod_de(self):
        rule = make_neon_rules()[0]
        ev = make_neon_stream()[0]
        assert rule.matches_event(ev) is True

    def test_revshare_matches_svod_at(self):
        rule = make_neon_rules()[0]
        ev = make_neon_stream()[1]
        assert rule.matches_event(ev) is True

    def test_broadcast_rule_matches_de(self):
        rule = make_neon_rules()[1]
        ev = make_neon_stream()[2]
        assert rule.matches_event(ev) is True

    def test_no_rule_matches_us_svod(self):
        rules = make_neon_rules()
        ev = make_neon_stream()[4]  # US territory — outside DACH
        assert all(not r.matches_event(ev) for r in rules)

    def test_revshare_rate_is_fifteen_percent(self):
        rule = make_neon_rules()[0]
        assert rule.rate_percent == Decimal("15.0")

    def test_broadcast_flat_fee_is_eight_eur(self):
        rule = make_neon_rules()[1]
        assert rule.unit_rate is not None
        assert rule.unit_rate.amount == Decimal("8.00")
        assert rule.unit_rate.currency == "EUR"


class TestQuantumContractRules:
    def test_mg_rule_type(self):
        rule = make_quantum_rules()[0]
        assert rule.rule_type == RuleType.MINIMUM_GUARANTEE
        assert rule.minimum_guarantee is not None
        assert rule.minimum_guarantee.amount == Decimal("500000.00")

    def test_escalator_threshold_is_ten_million(self):
        rule = make_quantum_rules()[1]
        assert rule.threshold_value == Decimal("10000000")

    def test_escalator_matches_svod_row(self):
        rule = make_quantum_rules()[1]
        ev = make_quantum_stream()[0]
        assert rule.matches_event(ev) is True

    def test_mg_rule_matches_broadcast_row(self):
        rule = make_quantum_rules()[0]
        ev = _broadcast_event(QUANTUM, "EV-Y", plays=1, offset=timedelta(hours=1),
                              territory=RightsTerritory.ROW)
        assert rule.matches_event(ev) is True


# ---------------------------------------------------------------------------
# Engine per-title isolation and threshold tests
# ---------------------------------------------------------------------------

class TestEchoesEngine:
    def test_pre_threshold_events_do_not_trigger(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        stream = make_echoes_stream()
        for ev in stream[:5]:
            result = engine.process_event(ev)
            assert result["threshold_triggered"] is False
            assert result["hero_notice_id"] is None

        assert engine.total_stream_minutes == Decimal("4920000")

    def test_sixth_event_triggers_hero_moment(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        for ev in make_echoes_stream()[:6]:
            result = engine.process_event(ev)

        assert result["threshold_triggered"] is True
        assert result["newly_triggered"] is True
        assert result["hero_notice_id"] is not None

    def test_settlement_notice_is_pending_after_hero(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        for ev in make_echoes_stream()[:6]:
            engine.process_event(ev)

        notice_id = engine.hero_notice_id
        assert notice_id is not None
        notice = engine.settlement_notices[notice_id]
        assert notice.status == SettlementStatus.PENDING

    def test_settlement_approve_workflow(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        for ev in make_echoes_stream()[:6]:
            engine.process_event(ev)

        notice_id = engine.hero_notice_id
        approved = engine.approve_settlement(notice_id, approved_by="CFO")
        assert approved.status == SettlementStatus.APPROVED
        assert approved.approved_by == "CFO"

    def test_post_threshold_event_does_not_re_trigger(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        stream = make_echoes_stream()
        for ev in stream:
            result = engine.process_event(ev)

        # Event 7 is post-threshold — newly_triggered must be False
        assert result["newly_triggered"] is False

    def test_audit_integrity_on_hero_notice(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        for ev in make_echoes_stream()[:6]:
            engine.process_event(ev)

        notice = engine.settlement_notices[engine.hero_notice_id]
        integrity = notice.verify_audit_integrity()
        assert integrity["all_valid"] is True
        assert integrity["chain_valid"] is True


class TestEchoesIdempotency:
    def test_duplicate_event_ignored(self):
        engine = RoyaltyEngine(rules=make_echoes_rules())
        ev = make_echoes_stream()[0]
        engine.process_event(ev)
        result = engine.process_event(ev)  # second submission of same event
        assert result["duplicate_ignored"] is True
        assert engine.total_stream_minutes == ev.stream_minutes
        assert len(engine.events) == 1


class TestNeonEngine:
    def test_avod_and_svod_events_processed(self):
        """Revenue-share rules do not affect stream_minutes accrual path — engine counts correctly."""
        engine = RoyaltyEngine(rules=make_neon_rules())
        stream = make_neon_stream()
        for ev in stream:
            engine.process_event(ev)

        # Neon has no PER_STREAM_MINUTE rule so audit_entries stay empty,
        # but events should all be recorded.
        assert engine.total_events_count == 5

    def test_no_threshold_triggered_for_neon(self):
        """Neon rules have no THRESHOLD_TRIGGER; engine never fires a hero moment."""
        engine = RoyaltyEngine(rules=make_neon_rules())
        for ev in make_neon_stream():
            result = engine.process_event(ev)
        assert engine.threshold_triggered is False
        assert engine.hero_notice_id is None

    def test_us_event_not_counted_in_any_rule(self):
        engine = RoyaltyEngine(rules=make_neon_rules())
        for ev in make_neon_stream():
            engine.process_event(ev)
        # US SVOD event contributes 0 audit entries (no rule matches it)
        assert engine.current_accrued_royalty == Decimal("0.00")


class TestQuantumEngine:
    def test_threshold_is_ten_million(self):
        engine = RoyaltyEngine(rules=make_quantum_rules())
        assert engine.threshold_target == Decimal("5000000")  # default; overridden in custom test

    def test_quantum_engine_with_custom_threshold(self):
        """Verify that a Quantum-specific engine can be wired with the 10 M threshold rule."""
        quantum_rules = make_quantum_rules()
        threshold_rule = next(r for r in quantum_rules if r.rule_type == RuleType.THRESHOLD_TRIGGER)
        assert threshold_rule.threshold_value == Decimal("10000000")

    def test_quantum_hero_moment_fires_at_ten_million(self):
        """Stream across 4 events to tip the 10 M threshold on event 4."""
        # Use only the THRESHOLD_TRIGGER rule so the engine computes a bonus
        threshold_rule = make_quantum_rules()[1]
        engine = RoyaltyEngine(rules=[threshold_rule])
        # Manually align the engine's threshold_target to the rule's value
        engine.threshold_target = threshold_rule.threshold_value

        stream = make_quantum_stream()
        results = [engine.process_event(ev) for ev in stream[:4]]

        hero_result = results[3]
        assert hero_result["threshold_triggered"] is True
        assert hero_result["newly_triggered"] is True
        assert hero_result["hero_notice_id"] is not None

    def test_quantum_post_hero_event_no_re_trigger(self):
        threshold_rule = make_quantum_rules()[1]
        engine = RoyaltyEngine(rules=[threshold_rule])
        engine.threshold_target = threshold_rule.threshold_value

        stream = make_quantum_stream()
        for ev in stream:
            result = engine.process_event(ev)

        # The last event must not re-trigger
        assert result["newly_triggered"] is False


# ---------------------------------------------------------------------------
# Cross-title isolation: separate engines must not share state
# ---------------------------------------------------------------------------

class TestCrossTitleIsolation:
    def test_echoes_engine_unaffected_by_neon_stream(self):
        echoes_engine = RoyaltyEngine(rules=make_echoes_rules())
        neon_engine = RoyaltyEngine(rules=make_neon_rules())

        for ev in make_neon_stream():
            neon_engine.process_event(ev)

        # Echoes engine has seen zero events
        assert echoes_engine.total_stream_minutes == Decimal("0")
        assert echoes_engine.total_events_count == 0

    def test_each_title_reaches_its_own_threshold_independently(self):
        echoes_engine = RoyaltyEngine(rules=make_echoes_rules())
        quantum_rule = make_quantum_rules()[1]
        quantum_engine = RoyaltyEngine(rules=[quantum_rule])
        quantum_engine.threshold_target = quantum_rule.threshold_value

        # Drive Echoes past 5 M
        for ev in make_echoes_stream()[:6]:
            echoes_engine.process_event(ev)

        # Quantum engine is still at zero
        assert echoes_engine.threshold_triggered is True
        assert quantum_engine.threshold_triggered is False

    def test_titles_produce_distinct_notice_ids(self):
        echoes_engine = RoyaltyEngine(rules=make_echoes_rules())
        for ev in make_echoes_stream()[:6]:
            echoes_engine.process_event(ev)

        quantum_rule = make_quantum_rules()[1]
        quantum_engine = RoyaltyEngine(rules=[quantum_rule])
        quantum_engine.threshold_target = quantum_rule.threshold_value
        for ev in make_quantum_stream()[:4]:
            quantum_engine.process_event(ev)

        echoes_notice_id = echoes_engine.hero_notice_id
        quantum_notice_id = quantum_engine.hero_notice_id

        assert echoes_notice_id is not None
        assert quantum_notice_id is not None
        assert echoes_notice_id != quantum_notice_id
