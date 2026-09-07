"""
residual_live.schemas
=====================
Core domain schemas for the Residual Live royalty pipeline.

Public surface:
  RoyaltyEvent      — one usage event arriving from the Confluent stream
  ContractRule      — a parsed clause from a licence agreement
  SettlementNotice  — an auditable payment obligation document
  AuditEntry        — immutable ledger entry used inside SettlementNotice
"""

from ._types import Money, compute_sha256
from .royalty_event import RoyaltyEvent, UsageChannel, RightsTerritory
from .contract_rule import ContractRule, RuleType, ThresholdBasis, ThresholdOperator
from .settlement_notice import SettlementNotice, SettlementStatus, AuditEntry

__all__ = [
    # RoyaltyEvent
    "RoyaltyEvent",
    "UsageChannel",
    "RightsTerritory",
    # ContractRule
    "ContractRule",
    "RuleType",
    "ThresholdBasis",
    "ThresholdOperator",
    # SettlementNotice
    "SettlementNotice",
    "SettlementStatus",
    "AuditEntry",
]
