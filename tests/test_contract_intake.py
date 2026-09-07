"""
tests/test_contract_intake.py
==============================
Unit & integration tests for the third Google ADK agent: Contract-Intake-Agent.
Validates extraction of operative royalty rules from SAG-AFTRA sample contract text.
"""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from residual_live.app import app
from residual_live.agents import (
    ContractIntakeOutput,
    ExtractedContractRule,
    build_contract_rules_from_intake,
    intake_contract_document,
)
from residual_live.demo_data import SAMPLE_SAG_AFTRA_AGREEMENT
from residual_live.schemas import RuleType


@pytest.fixture
def client():
    return TestClient(app)


def test_contract_intake_output_schema():
    sample_rule1 = ExtractedContractRule(
        rule_id="RULE-SVOD-BASE",
        rule_name="Base SVOD Stream Rate",
        rule_type="per_stream_minute",
        clause_reference="Clause 4.1",
        channel="svod",
        territory="US",
        unit_rate_amount=0.0015,
        notes="Base per-minute streaming rate",
    )
    sample_rule2 = ExtractedContractRule(
        rule_id="RULE-HERO-BONUS",
        rule_name="5M Milestone Escalator",
        rule_type="threshold_trigger",
        clause_reference="Clause 4.2",
        channel="svod",
        territory="US",
        threshold_value=5000000.0,
        bonus_amount=25000.0,
        notes="High-volume milestone bonus",
    )
    intake = ContractIntakeOutput(
        contract_id="AGR-SAG-DGA-2026-088",
        title_name="Echoes of Eternity",
        licensor="Sovereign Media Rights LLC",
        licensee="Global Cinema Distribution Corp",
        governing_guild="SAG-AFTRA",
        extracted_rules=[sample_rule1, sample_rule2],
    )

    domain_rules = build_contract_rules_from_intake(intake)
    assert len(domain_rules) == 2
    assert domain_rules[0].rule_type == RuleType.PER_STREAM_MINUTE
    assert domain_rules[0].unit_rate.amount == Decimal("0.0015")
    assert domain_rules[1].rule_type == RuleType.THRESHOLD_TRIGGER
    assert domain_rules[1].threshold_value == Decimal("5000000")


def test_api_contract_sample_endpoint(client):
    res = client.get("/api/contract/sample")
    assert res.status_code == 200
    data = res.json()
    assert "sample_text" in data
    assert "SAG-AFTRA" in data["sample_text"]
    assert "Clause 4.1" in data["sample_text"] or "4.1" in data["sample_text"]


from residual_live.config import settings


def test_api_contract_intake_auth(client):
    """Verify that POST /api/contract/intake requires X-Demo-Key header."""
    res = client.post(
        "/api/contract/intake",
        json={"contract_text": SAMPLE_SAG_AFTRA_AGREEMENT},
    )
    assert res.status_code == 401

    res_invalid = client.post(
        "/api/contract/intake",
        headers={"X-Demo-Key": "wrong-key"},
        json={"contract_text": SAMPLE_SAG_AFTRA_AGREEMENT},
    )
    assert res_invalid.status_code == 401


def test_api_contract_intake_e2e(client):
    """Test full e2e contract intake endpoint running Google ADK agent with valid Demo Key."""
    res = client.post(
        "/api/contract/intake",
        headers={"X-Demo-Key": settings.DEMO_KEY},
        json={"contract_text": SAMPLE_SAG_AFTRA_AGREEMENT},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["rules_count"] >= 2
    assert "contract" in data
    assert len(data["rules"]) >= 2

