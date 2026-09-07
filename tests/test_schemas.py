"""
tests/test_schemas.py
=====================
Self-contained pytest suite for the three core domain schemas.

Covers:
  * Money precision and currency normalisation
  * compute_sha256 determinism
  * RoyaltyEvent construction and channel/metric mutual-exclusion validation
  * ContractRule construction, rate-field validation, temporal validity, matches_event
  * AuditEntry.create() hash and verify()
  * SettlementNotice.create() — totals, hashes, currency consistency
  * verify_audit_integrity() — green path and tampered entry/chain/notice
  * Workflow transitions: submit_for_approval / approve / reject guard rails
"""

from __future__ import annotations

import sys
import os

# Allow running from the product/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from residual_live.schemas._types import Money, compute_sha256
from residual_live.schemas.royalty_event import (
    RoyaltyEvent,
    UsageChannel,
    RightsTerritory,
)
from residual_live.schemas.contract_rule import (
    ContractRule,
    RuleType,
    ThresholdBasis,
    ThresholdOperator,
)
from residual_live.schemas.settlement_notice import (
    AuditEntry,
    SettlementNotice,
    SettlementStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

UTC = timezone.utc

T0 = datetime(2026, 9, 7, 14, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 7, 14, 30, 0, tzinfo=UTC)
T_FROM = datetime(2025, 1, 1, tzinfo=UTC)
T_UNTIL = datetime(2027, 1, 1, tzinfo=UTC)
T_PERIOD_FROM = datetime(2026, 9, 1, tzinfo=UTC)
T_PERIOD_UNTIL = datetime(2026, 10, 1, tzinfo=UTC)

USD = "USD"
EUR = "EUR"


def make_svod_event(
    stream_minutes: Decimal = Decimal("95.5"),
    contract_id: str = "CONTRACT-001",
    territory: RightsTerritory = RightsTerritory.DE,
) -> RoyaltyEvent:
    return RoyaltyEvent(
        title_id="TITLE-001",
        title_name="The Last Frontier",
        contract_id=contract_id,
        channel=UsageChannel.SVOD,
        territory=territory,
        stream_minutes=stream_minutes,
        occurred_at=T0,
        licence_fee_currency=USD,
    )


def make_broadcast_event(play_count: int = 3) -> RoyaltyEvent:
    return RoyaltyEvent(
        title_id="TITLE-001",
        title_name="The Last Frontier",
        contract_id="CONTRACT-001",
        channel=UsageChannel.BROADCAST,
        territory=RightsTerritory.DE,
        play_count=play_count,
        occurred_at=T0,
        licence_fee_currency=USD,
    )


def make_threshold_rule(
    threshold_value: Decimal = Decimal("100000"),
    unit_rate_amount: Decimal = Decimal("0.0012"),
) -> ContractRule:
    return ContractRule(
        rule_id="RULE-001",
        contract_id="CONTRACT-001",
        clause_reference="§ 4.2 (b)",
        rule_type=RuleType.THRESHOLD_TRIGGER,
        channels=[UsageChannel.SVOD, UsageChannel.AVOD],
        territories=[RightsTerritory.DE, RightsTerritory.AT, RightsTerritory.CH],
        effective_from=T_FROM,
        effective_until=T_UNTIL,
        threshold_basis=ThresholdBasis.STREAM_MINUTES,
        threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=threshold_value,
        unit_rate=Money(amount=unit_rate_amount, currency=USD),
    )


def make_audit_entry(
    entry_index: int = 0,
    event_id: str = "EVT-001",
    amount: Decimal = Decimal("114.60"),
) -> AuditEntry:
    return AuditEntry.create(
        entry_index=entry_index,
        event_id=event_id,
        occurred_at=T0,
        rule_id="RULE-001",
        clause_reference="§ 4.2 (b)",
        usage_metric_label="95500 stream_minutes",
        contribution=Money(amount=amount, currency=USD),
        computation_note="95500 min × USD 0.0012/min",
    )


def make_notice(audit_log: list[AuditEntry] | None = None) -> SettlementNotice:
    log = audit_log or [make_audit_entry()]
    return SettlementNotice.create(
        title_id="TITLE-001",
        title_name="The Last Frontier",
        contract_id="CONTRACT-001",
        licensor_id="LICENSOR-42",
        licensor_name="Frontier Studios GmbH",
        licensee_id="LICENSEE-NF-42",
        licensee_name="StreamCo Europe",
        period_from=T_PERIOD_FROM,
        period_until=T_PERIOD_UNTIL,
        currency=USD,
        audit_log=log,
    )


# ---------------------------------------------------------------------------
# Money tests
# ---------------------------------------------------------------------------

class TestMoney:
    def test_two_decimal_rounding(self):
        m = Money(amount=Decimal("12.3456"), currency="usd")
        assert m.amount == Decimal("12.35")

    def test_currency_uppercased(self):
        m = Money(amount=Decimal("10"), currency="eur")
        assert m.currency == "EUR"

    def test_frozen(self):
        m = Money(amount=Decimal("10"), currency=USD)
        with pytest.raises(Exception):
            m.amount = Decimal("99")  # type: ignore

    def test_addition_same_currency(self):
        a = Money(amount=Decimal("10.00"), currency=USD)
        b = Money(amount=Decimal("5.50"), currency=USD)
        assert (a + b).amount == Decimal("15.50")

    def test_addition_currency_mismatch(self):
        a = Money(amount=Decimal("10.00"), currency=USD)
        b = Money(amount=Decimal("10.00"), currency=EUR)
        with pytest.raises(ValueError, match="Cannot add"):
            a + b

    def test_invalid_currency_code(self):
        with pytest.raises(Exception):
            Money(amount=Decimal("10"), currency="US")  # too short

    def test_invalid_lowercase_pattern(self):
        # Pattern requires [A-Z]{3} — lowercase should fail after the validator
        # (the validator uppercases, so "us1" should fail the pattern)
        with pytest.raises(Exception):
            Money(amount=Decimal("10"), currency="US1")


# ---------------------------------------------------------------------------
# compute_sha256 tests
# ---------------------------------------------------------------------------

class TestComputeSha256:
    def test_deterministic(self):
        payload = {"a": "1", "b": 2}
        assert compute_sha256(payload) == compute_sha256(payload)

    def test_key_order_independent(self):
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        assert compute_sha256(a) == compute_sha256(b)

    def test_different_payloads_differ(self):
        assert compute_sha256({"a": 1}) != compute_sha256({"a": 2})

    def test_decimal_serialised_as_string(self):
        # str(Decimal("1.50")) == "1.50" and str(Decimal("1.5")) == "1.5" —
        # different strings, different hashes.  The hash function is faithful
        # to the exact Decimal representation; callers must normalise first.
        d1 = {"v": Decimal("1.50")}
        d2 = {"v": Decimal("1.50")}  # identical repr → same hash
        assert compute_sha256(d1) == compute_sha256(d2)
        # Different repr → different hash (expected behaviour)
        assert compute_sha256({"v": Decimal("1.5")}) != compute_sha256({"v": Decimal("1.50")})


# ---------------------------------------------------------------------------
# RoyaltyEvent tests
# ---------------------------------------------------------------------------

class TestRoyaltyEvent:
    def test_svod_valid(self):
        e = make_svod_event()
        assert e.channel == UsageChannel.SVOD
        assert e.stream_minutes == Decimal("95.5")
        assert e.play_count is None

    def test_broadcast_valid(self):
        e = make_broadcast_event()
        assert e.channel == UsageChannel.BROADCAST
        assert e.play_count == 3
        assert e.stream_minutes is None

    def test_svod_requires_stream_minutes(self):
        with pytest.raises(ValueError, match="requires stream_minutes"):
            RoyaltyEvent(
                title_id="T",
                title_name="X",
                contract_id="C",
                channel=UsageChannel.SVOD,
                territory=RightsTerritory.DE,
                occurred_at=T0,
                licence_fee_currency=USD,
                # stream_minutes omitted
            )

    def test_svod_rejects_play_count(self):
        with pytest.raises(ValueError, match="must not set play_count"):
            RoyaltyEvent(
                title_id="T",
                title_name="X",
                contract_id="C",
                channel=UsageChannel.SVOD,
                territory=RightsTerritory.DE,
                occurred_at=T0,
                licence_fee_currency=USD,
                stream_minutes=Decimal("50"),
                play_count=2,
            )

    def test_broadcast_requires_play_count(self):
        with pytest.raises(ValueError, match="requires play_count"):
            RoyaltyEvent(
                title_id="T",
                title_name="X",
                contract_id="C",
                channel=UsageChannel.BROADCAST,
                territory=RightsTerritory.DE,
                occurred_at=T0,
                licence_fee_currency=USD,
                # play_count omitted
            )

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            RoyaltyEvent(
                title_id="T",
                title_name="X",
                contract_id="C",
                channel=UsageChannel.SVOD,
                territory=RightsTerritory.DE,
                occurred_at=datetime(2026, 9, 7, 14, 0, 0),  # naive
                licence_fee_currency=USD,
                stream_minutes=Decimal("50"),
            )

    def test_svod_zero_stream_minutes_rejected(self):
        with pytest.raises(ValueError, match="stream_minutes must be positive"):
            RoyaltyEvent(
                title_id="T",
                title_name="X",
                contract_id="C",
                channel=UsageChannel.SVOD,
                territory=RightsTerritory.DE,
                occurred_at=T0,
                licence_fee_currency=USD,
                stream_minutes=Decimal("0"),
            )

    def test_event_is_frozen(self):
        e = make_svod_event()
        with pytest.raises(Exception):
            e.title_id = "MUTATED"  # type: ignore


# ---------------------------------------------------------------------------
# ContractRule tests
# ---------------------------------------------------------------------------

class TestContractRule:
    def test_threshold_rule_valid(self):
        r = make_threshold_rule()
        assert r.rule_type == RuleType.THRESHOLD_TRIGGER
        assert r.unit_rate is not None

    def test_threshold_missing_unit_rate(self):
        with pytest.raises(ValueError, match="requires unit_rate"):
            ContractRule(
                rule_id="R",
                contract_id="C",
                clause_reference="§ 1",
                rule_type=RuleType.THRESHOLD_TRIGGER,
                channels=[UsageChannel.SVOD],
                territories=[RightsTerritory.DE],
                effective_from=T_FROM,
                threshold_basis=ThresholdBasis.STREAM_MINUTES,
                threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
                threshold_value=Decimal("100000"),
                # unit_rate missing
            )

    def test_threshold_missing_threshold_value(self):
        with pytest.raises(ValueError, match="requires: threshold_value"):
            ContractRule(
                rule_id="R",
                contract_id="C",
                clause_reference="§ 1",
                rule_type=RuleType.THRESHOLD_TRIGGER,
                channels=[UsageChannel.SVOD],
                territories=[RightsTerritory.DE],
                effective_from=T_FROM,
                unit_rate=Money(amount=Decimal("0.001"), currency=USD),
                threshold_basis=ThresholdBasis.STREAM_MINUTES,
                threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
                # threshold_value missing
            )

    def test_revenue_share_requires_rate_percent(self):
        with pytest.raises(ValueError, match="requires rate_percent"):
            ContractRule(
                rule_id="R",
                contract_id="C",
                clause_reference="§ 2",
                rule_type=RuleType.REVENUE_SHARE,
                channels=[UsageChannel.SVOD],
                territories=[RightsTerritory.DE],
                effective_from=T_FROM,
                # rate_percent missing
            )

    def test_pro_rata_requires_pool_total(self):
        with pytest.raises(ValueError, match="requires pool_total"):
            ContractRule(
                rule_id="R",
                contract_id="C",
                clause_reference="§ 3",
                rule_type=RuleType.PRO_RATA,
                channels=[UsageChannel.AVOD],
                territories=[RightsTerritory.DE],
                effective_from=T_FROM,
                # pool_total missing
            )

    def test_temporal_window_invalid(self):
        with pytest.raises(ValueError, match="effective_until must be strictly after"):
            ContractRule(
                rule_id="R",
                contract_id="C",
                clause_reference="§ 1",
                rule_type=RuleType.FLAT_FEE_PER_PLAY,
                channels=[UsageChannel.BROADCAST],
                territories=[RightsTerritory.DE],
                effective_from=T_UNTIL,
                effective_until=T_FROM,  # before effective_from
                unit_rate=Money(amount=Decimal("100"), currency=USD),
            )

    def test_is_active_at(self):
        r = make_threshold_rule()
        assert r.is_active_at(T0) is True
        assert r.is_active_at(datetime(2024, 12, 31, tzinfo=UTC)) is False
        assert r.is_active_at(datetime(2027, 1, 1, tzinfo=UTC)) is False

    def test_matches_event_svod_de(self):
        r = make_threshold_rule()
        e = make_svod_event()
        assert r.matches_event(e) is True

    def test_matches_event_wrong_channel(self):
        r = make_threshold_rule()
        e = make_broadcast_event()
        assert r.matches_event(e) is False

    def test_matches_event_row_catches_all(self):
        r = ContractRule(
            rule_id="R-ROW",
            contract_id="CONTRACT-001",
            clause_reference="§ 5",
            rule_type=RuleType.FLAT_FEE_PER_PLAY,
            channels=[UsageChannel.BROADCAST],
            territories=[RightsTerritory.ROW],
            effective_from=T_FROM,
            unit_rate=Money(amount=Decimal("50"), currency=USD),
        )
        e = make_broadcast_event()  # territory=DE, but ROW catches all
        assert r.matches_event(e) is True

    def test_rule_is_frozen(self):
        r = make_threshold_rule()
        with pytest.raises(Exception):
            r.rule_id = "MUTATED"  # type: ignore


# ---------------------------------------------------------------------------
# AuditEntry tests
# ---------------------------------------------------------------------------

class TestAuditEntry:
    def test_create_computes_hash(self):
        entry = make_audit_entry()
        assert len(entry.entry_hash) == 64  # SHA-256 hex

    def test_verify_passes_on_fresh_entry(self):
        assert make_audit_entry().verify() is True

    def test_verify_fails_after_mutation(self):
        entry = make_audit_entry()
        # Bypass frozen model by constructing a tampered copy via model_copy
        tampered = entry.model_copy(
            update={"contribution": Money(amount=Decimal("999.99"), currency=USD)}
        )
        assert tampered.verify() is False

    def test_different_indices_produce_different_hashes(self):
        e0 = make_audit_entry(entry_index=0)
        e1 = make_audit_entry(entry_index=1)
        assert e0.entry_hash != e1.entry_hash


# ---------------------------------------------------------------------------
# SettlementNotice tests
# ---------------------------------------------------------------------------

class TestSettlementNotice:
    def test_create_single_entry(self):
        n = make_notice()
        assert n.gross_royalty_due == Money(amount=Decimal("114.60"), currency=USD)
        assert n.net_royalty_due == Money(amount=Decimal("114.60"), currency=USD)
        assert n.status == SettlementStatus.DRAFT

    def test_create_multiple_entries_sums_correctly(self):
        entries = [
            make_audit_entry(entry_index=0, amount=Decimal("100.00")),
            make_audit_entry(entry_index=1, event_id="EVT-002", amount=Decimal("50.25")),
        ]
        n = make_notice(audit_log=entries)
        assert n.gross_royalty_due.amount == Decimal("150.25")

    def test_withholding_tax_deducted(self):
        entry = make_audit_entry(amount=Decimal("200.00"))
        wht = Money(amount=Decimal("30.00"), currency=USD)
        n = SettlementNotice.create(
            title_id="T",
            title_name="X",
            contract_id="C",
            licensor_id="L1",
            licensor_name="Licensor",
            licensee_id="L2",
            licensee_name="Licensee",
            period_from=T_PERIOD_FROM,
            period_until=T_PERIOD_UNTIL,
            currency=USD,
            audit_log=[entry],
            withholding_tax=wht,
        )
        assert n.net_royalty_due.amount == Decimal("170.00")

    def test_currency_mismatch_in_entry_rejected(self):
        entry = AuditEntry.create(
            entry_index=0,
            event_id="EVT-X",
            occurred_at=T0,
            rule_id="RULE-001",
            clause_reference="§ 1",
            usage_metric_label="10 plays",
            contribution=Money(amount=Decimal("50.00"), currency=EUR),  # EUR ≠ USD
            computation_note="10 × 5 EUR",
        )
        with pytest.raises(ValueError, match="does not match notice currency"):
            make_notice(audit_log=[entry])

    def test_period_invalid(self):
        with pytest.raises(ValueError, match="period_until must be strictly after"):
            SettlementNotice.create(
                title_id="T",
                title_name="X",
                contract_id="C",
                licensor_id="L1",
                licensor_name="Licensor",
                licensee_id="L2",
                licensee_name="Licensee",
                period_from=T_PERIOD_UNTIL,   # swapped
                period_until=T_PERIOD_FROM,
                currency=USD,
                audit_log=[make_audit_entry()],
            )

    def test_empty_audit_log_rejected(self):
        with pytest.raises(ValueError, match="at least one entry"):
            SettlementNotice.create(
                title_id="T",
                title_name="X",
                contract_id="C",
                licensor_id="L1",
                licensor_name="Licensor",
                licensee_id="L2",
                licensee_name="Licensee",
                period_from=T_PERIOD_FROM,
                period_until=T_PERIOD_UNTIL,
                currency=USD,
                audit_log=[],
            )


# ---------------------------------------------------------------------------
# verify_audit_integrity tests
# ---------------------------------------------------------------------------

class TestVerifyAuditIntegrity:
    def test_fresh_notice_passes(self):
        result = make_notice().verify_audit_integrity()
        assert result["all_valid"] is True
        assert result["failed_entry_indices"] == []

    def test_tampered_entry_detected(self):
        notice = make_notice()
        # Tamper one entry hash by reconstructing the list with a corrupted entry
        bad_entry = notice.audit_log[0].model_copy(update={"entry_hash": "deadbeef"})
        # Bypass Pydantic validation by using model_copy on the notice
        tampered_notice = notice.model_copy(update={"audit_log": [bad_entry]})
        result = tampered_notice.verify_audit_integrity()
        assert result["entries_valid"] is False
        assert 0 in result["failed_entry_indices"]

    def test_tampered_chain_hash_detected(self):
        notice = make_notice()
        tampered = notice.model_copy(update={"audit_chain_hash": "badhash"})
        result = tampered.verify_audit_integrity()
        assert result["chain_valid"] is False

    def test_tampered_notice_hash_detected(self):
        notice = make_notice()
        tampered = notice.model_copy(update={"notice_hash": "badhash"})
        result = tampered.verify_audit_integrity()
        assert result["notice_valid"] is False

    def test_tampered_gross_amount_detected(self):
        notice = make_notice()
        tampered = notice.model_copy(
            update={"gross_royalty_due": Money(amount=Decimal("999999.00"), currency=USD)}
        )
        result = tampered.verify_audit_integrity()
        assert result["notice_valid"] is False


# ---------------------------------------------------------------------------
# Workflow transition tests
# ---------------------------------------------------------------------------

class TestWorkflowTransitions:
    def test_draft_to_pending(self):
        n = make_notice()
        pending = n.submit_for_approval()
        assert pending.status == SettlementStatus.PENDING

    def test_pending_to_approved(self):
        n = make_notice().submit_for_approval()
        approved = n.approve(approved_by="user-cfo-01")
        assert approved.status == SettlementStatus.APPROVED
        assert approved.approved_by == "user-cfo-01"
        assert approved.approved_at is not None

    def test_pending_to_rejected(self):
        n = make_notice().submit_for_approval()
        rejected = n.reject(reason="Incorrect period dates")
        assert rejected.status == SettlementStatus.REJECTED
        assert rejected.rejection_reason == "Incorrect period dates"

    def test_cannot_approve_draft(self):
        with pytest.raises(ValueError, match="PENDING notice"):
            make_notice().approve(approved_by="user-01")

    def test_cannot_reject_draft(self):
        with pytest.raises(ValueError, match="PENDING notice"):
            make_notice().reject(reason="bad")

    def test_cannot_submit_non_draft(self):
        pending = make_notice().submit_for_approval()
        with pytest.raises(ValueError, match="DRAFT notice"):
            pending.submit_for_approval()

    def test_approve_is_immutable_new_object(self):
        n = make_notice().submit_for_approval()
        approved = n.approve(approved_by="u")
        assert n.status == SettlementStatus.PENDING  # original unchanged
        assert approved.status == SettlementStatus.APPROVED
