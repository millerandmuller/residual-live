"""
residual_live.engine
====================
Real-time royalty accrual engine, threshold monitor, and settlement generator.
Powers the live Hero Moment when streaming volume triggers contract escalators.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Dict, List, Optional
import uuid

from .schemas import (
    AuditEntry,
    ContractRule,
    Money,
    RightsTerritory,
    RoyaltyEvent,
    RuleType,
    SettlementNotice,
    SettlementStatus,
    ThresholdBasis,
    ThresholdOperator,
    UsageChannel,
)

logger = logging.getLogger("residual_live.engine")

SAMPLE_TITLE_ID = "TITLE-ECHOES-2026"
SAMPLE_TITLE_NAME = "Echoes of Eternity"
SAMPLE_CONTRACT_ID = "AGR-SAG-DGA-2026-088"
SAMPLE_PARTY_A = "Sovereign Media Rights LLC"
SAMPLE_PARTY_B = "Global Cinema Distribution Corp"

T_EFFECTIVE = datetime(2025, 1, 1, tzinfo=timezone.utc)

SAMPLE_RULES = [
    ContractRule(
        rule_id="RULE-CLAUSE-4.1-BASE",
        contract_id=SAMPLE_CONTRACT_ID,
        clause_reference="Clause 4.1 (Base SVOD Streaming Rate)",
        rule_type=RuleType.PER_STREAM_MINUTE,
        channels=[UsageChannel.SVOD],
        territories=[RightsTerritory.US, RightsTerritory.ROW],
        effective_from=T_EFFECTIVE,
        unit_rate=Money(amount=Decimal("0.0015"), currency="USD"),
        display_label="Base SVOD Tier $0.0015/min",
    ),
    ContractRule(
        rule_id="RULE-CLAUSE-4.2-HERO-THRESHOLD",
        contract_id=SAMPLE_CONTRACT_ID,
        clause_reference="Clause 4.2: If the Title achieves 5,000,000 or more stream minutes in the US and ROW territories, Licensee shall pay Licensor a fixed one-time milestone bonus of $25,000.",
        rule_type=RuleType.THRESHOLD_TRIGGER,
        channels=[UsageChannel.SVOD],
        territories=[RightsTerritory.US, RightsTerritory.ROW],
        effective_from=T_EFFECTIVE,
        threshold_basis=ThresholdBasis.STREAM_MINUTES,
        threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
        threshold_value=Decimal("5000000"),
        unit_rate=Money(amount=Decimal("0.0050"), currency="USD"),
        apply_rate_to_full_accumulation=True,
        display_label="Milestone Escalator ≥ 5M stream minutes",
    ),
]


class RoyaltyEngine:
    """Accumulates incoming royalty events, tests threshold conditions, and issues auditable settlements."""

    def __init__(self, rules: Optional[List[ContractRule]] = None):
        self.rules: List[ContractRule] = rules or SAMPLE_RULES
        self.events: List[RoyaltyEvent] = []
        self.audit_entries: List[AuditEntry] = []
        self.settlement_notices: Dict[str, SettlementNotice] = {}

        # Aggregated metrics
        self.total_stream_minutes: Decimal = Decimal("0")
        self.total_plays: int = 0
        self.total_events_count: int = 0
        self.current_accrued_royalty: Decimal = Decimal("0.00")

        # Threshold tracking
        self.threshold_target: Decimal = Decimal("5000000")
        self.threshold_triggered: bool = False
        self.hero_moment_occurred: bool = False
        self.hero_notice_id: Optional[str] = None
        self.processed_event_ids: set[str] = set()

    def process_event(self, event: RoyaltyEvent) -> Dict[str, any]:
        """Process a single incoming event, update running tally, and check threshold."""
        if event.event_id in self.processed_event_ids:
            return {
                "event_id": event.event_id,
                "total_stream_minutes": int(self.total_stream_minutes),
                "threshold_progress_pct": min(100.0, float(self.total_stream_minutes / self.threshold_target * 100)),
                "current_accrued_royalty": float(self.current_accrued_royalty),
                "threshold_triggered": self.threshold_triggered,
                "newly_triggered": False,
                "hero_notice_id": self.hero_notice_id,
                "duplicate_ignored": True,
            }
        self.processed_event_ids.add(event.event_id)

        self.events.append(event)
        self.total_events_count += 1

        if event.stream_minutes:
            self.total_stream_minutes += event.stream_minutes
        if event.play_count:
            self.total_plays += event.play_count

        event_contribution = Decimal("0.00")

        # Evaluate rules
        for rule in self.rules:
            if not rule.matches_event(event):
                continue

            if rule.rule_type == RuleType.PER_STREAM_MINUTE and event.stream_minutes and rule.unit_rate:
                amount = (event.stream_minutes * rule.unit_rate.amount).quantize(Decimal("0.01"))
                event_contribution += amount
                audit_entry = AuditEntry.create(
                    entry_index=len(self.audit_entries),
                    event_id=event.event_id,
                    occurred_at=event.occurred_at,
                    rule_id=rule.rule_id,
                    clause_reference=rule.clause_reference,
                    usage_metric_label=f"{event.stream_minutes} stream_minutes",
                    contribution=Money(amount=amount, currency="USD"),
                    computation_note=f"{event.stream_minutes} min × USD {rule.unit_rate.amount}/min",
                )
                self.audit_entries.append(audit_entry)

        self.current_accrued_royalty += event_contribution

        # Check Threshold Trigger (The Hero Moment)
        newly_triggered = False
        if not self.threshold_triggered and self.total_stream_minutes >= self.threshold_target:
            self.threshold_triggered = True
            newly_triggered = True
            self.hero_moment_occurred = True

            # Trigger Hero Settlement Notice & Escalator Bonus ($25,000 Milestone Bonus)
            hero_rule = next((r for r in self.rules if r.rule_type == RuleType.THRESHOLD_TRIGGER), None)
            
            clause_text = hero_rule.clause_reference if hero_rule else "Clause 4.2"
            
            # Deterministic truth from ContractRule
            if hero_rule and hero_rule.unit_rate and hero_rule.threshold_value and hero_rule.apply_rate_to_full_accumulation:
                true_bonus_amount = hero_rule.threshold_value * hero_rule.unit_rate.amount
            else:
                true_bonus_amount = Decimal("25000.00")

            # Agent 1: Klausel-Leser zur Vertragsanalyse (Cross-Check)
            from .agents import analyze_contract_clause, generate_settlement_message
            analysis = analyze_contract_clause(clause_text)
            agent_bonus_amount = Decimal(str(analysis.bonus_amount)) if analysis.is_applicable else Decimal("0.00")
            
            # Governance Cross-Check
            if true_bonus_amount == agent_bonus_amount:
                verification_flag = "[VERIFIED: agent-checked against clause]"
            else:
                verification_flag = f"[WARN: agent extraction mismatch - agent found ${agent_bonus_amount}, rule dictates ${true_bonus_amount}]"
                
            bonus_amount = true_bonus_amount
                
            # Agent 2: Bezifferung/Mitteilungserstellung
            settlement_message = generate_settlement_message(
                clause_text=clause_text,
                total_stream_minutes=int(self.total_stream_minutes),
                bonus_amount=bonus_amount,
                verification_flag=verification_flag
            )

            milestone_entry = AuditEntry.create(
                entry_index=len(self.audit_entries),
                event_id=f"TRIGGER-{event.event_id}",
                occurred_at=datetime.now(timezone.utc),
                rule_id=hero_rule.rule_id if hero_rule else "RULE-HERO",
                clause_reference=clause_text,
                usage_metric_label=f"{self.total_stream_minutes} stream_minutes threshold reached",
                contribution=Money(amount=bonus_amount, currency="USD"),
                computation_note=f"ADK Agent: {settlement_message}",
            )
            self.audit_entries.append(milestone_entry)
            self.current_accrued_royalty += bonus_amount

            notice_id = f"SETTLE-LIVE-{uuid.uuid4().hex[:8].upper()}"
            period_until = max(event.occurred_at + timedelta(seconds=1), self.events[0].occurred_at + timedelta(seconds=1))

            hero_notice = SettlementNotice.create(
                notice_id=notice_id,
                title_id=SAMPLE_TITLE_ID,
                title_name=SAMPLE_TITLE_NAME,
                contract_id=SAMPLE_CONTRACT_ID,
                licensor_id="LICENSOR-SOVEREIGN",
                licensor_name=SAMPLE_PARTY_A,
                licensee_id="LICENSEE-GLOBAL",
                licensee_name=SAMPLE_PARTY_B,
                period_from=self.events[0].occurred_at,
                period_until=period_until,
                currency="USD",
                audit_log=list(self.audit_entries),
            )
            # Submit to pending approval
            hero_notice = hero_notice.submit_for_approval()
            self.settlement_notices[notice_id] = hero_notice
            self.hero_notice_id = notice_id
            logger.info(f"*** HERO MOMENT *** Settlement notice {notice_id} generated at {self.total_stream_minutes:,} minutes!")

        progress_pct = float(min(Decimal("100.0"), ((self.total_stream_minutes / self.threshold_target) * Decimal("100"))))

        return {
            "event_id": event.event_id,
            "total_stream_minutes": int(self.total_stream_minutes),
            "threshold_progress_pct": round(progress_pct, 2),
            "current_accrued_royalty": float(self.current_accrued_royalty),
            "threshold_triggered": self.threshold_triggered,
            "newly_triggered": newly_triggered,
            "hero_notice_id": self.hero_notice_id if newly_triggered else None,
        }

    def approve_settlement(self, notice_id: str, approved_by: str = "Chris") -> Optional[SettlementNotice]:
        """Human-in-the-Loop: 1-click approve a pending settlement notice."""
        notice = self.settlement_notices.get(notice_id)
        if not notice:
            return None
        approved = notice.approve(approved_by=approved_by)
        self.settlement_notices[notice_id] = approved
        return approved

    def get_state_summary(self) -> dict:
        progress_pct = float(min(Decimal("100.0"), ((self.total_stream_minutes / self.threshold_target) * Decimal("100"))))
        return {
            "title_id": SAMPLE_TITLE_ID,
            "title_name": SAMPLE_TITLE_NAME,
            "contract_id": SAMPLE_CONTRACT_ID,
            "licensor": SAMPLE_PARTY_A,
            "licensee": SAMPLE_PARTY_B,
            "total_stream_minutes": int(self.total_stream_minutes),
            "threshold_target": int(self.threshold_target),
            "threshold_progress_pct": round(progress_pct, 2),
            "current_accrued_royalty": float(self.current_accrued_royalty),
            "events_processed": self.total_events_count,
            "threshold_triggered": self.threshold_triggered,
            "hero_moment_occurred": self.hero_moment_occurred,
            "hero_notice_id": self.hero_notice_id,
            "settlements_count": len(self.settlement_notices),
        }
