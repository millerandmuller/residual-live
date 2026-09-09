"""
tests/test_engine_and_api.py
============================
Unit & integration tests for the real-time RoyaltyEngine, demo streaming, and API endpoints.
"""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient

from residual_live.app import app
from residual_live.config import settings
from residual_live.demo_data import create_curated_demo_stream
from residual_live.engine import RoyaltyEngine
from residual_live.schemas import RightsTerritory, RoyaltyEvent, SettlementStatus, UsageChannel


@pytest.fixture
def client():
    return TestClient(app)


def test_engine_accrual_and_hero_moment():
    engine = RoyaltyEngine()
    events = create_curated_demo_stream()

    # Step 1: Process first 5 events (under 5M minutes)
    for ev in events[:5]:
        res = engine.process_event(ev)
        assert res["threshold_triggered"] is False
        assert res["hero_notice_id"] is None

    assert engine.total_stream_minutes == 4920000
    assert engine.threshold_triggered is False

    # Step 2: Process the 6th event (The Hero Tipping Point: +120k mins -> 5.04M)
    hero_res = engine.process_event(events[5])
    assert hero_res["threshold_triggered"] is True
    assert hero_res["newly_triggered"] is True
    assert hero_res["hero_notice_id"] is not None

    notice_id = hero_res["hero_notice_id"]
    notice = engine.settlement_notices[notice_id]
    assert notice.status == SettlementStatus.PENDING

    # Verify cryptographic integrity of the notice
    integrity = notice.verify_audit_integrity()
    assert integrity["all_valid"] is True
    assert integrity["chain_valid"] is True
    assert integrity["notice_valid"] is True

    # Step 3: 1-Click Human Approval
    approved = engine.approve_settlement(notice_id, approved_by="Chris")
    assert approved.status == SettlementStatus.APPROVED
    assert approved.approved_by == "Chris"
    assert approved.approved_at is not None


def test_api_status_and_demo_endpoints(client):
    # Test status
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "total_stream_minutes" in data
    assert "threshold_target" in data
    assert data["threshold_target"] == 5000000

    # Test Bob audit endpoint
    res_bob = client.get("/api/bob-audit")
    assert res_bob.status_code == 200
    bob_data = res_bob.json()
    assert bob_data["task_id"] == "e1935a4d4dfe486aa3290acaa2f66f57"
    assert bob_data["tests_passed"] == 90

    # Test unauthorized POST without X-Demo-Key
    res_unauth = client.post("/api/demo/step")
    assert res_unauth.status_code == 401
    res_bad = client.post("/api/demo/step", headers={"X-Demo-Key": "wrong-key"})
    assert res_bad.status_code == 401

    # Test authorized demo step
    headers = {"X-Demo-Key": settings.DEMO_KEY}
    res_step = client.post("/api/demo/step", headers=headers)
    assert res_step.status_code == 200
    step_data = res_step.json()
    assert "processed_event" in step_data

    # Test authorized reset
    res_reset = client.post("/api/demo/reset", headers=headers)
    assert res_reset.status_code == 200
    reset_data = res_reset.json()
    assert reset_data["summary"]["total_stream_minutes"] == 0


def test_engine_idempotency():
    engine = RoyaltyEngine()
    events = create_curated_demo_stream()
    ev0 = events[0]

    # Process first time
    res1 = engine.process_event(ev0)
    assert res1.get("duplicate_ignored") is not True
    assert engine.total_stream_minutes == ev0.stream_minutes

    # Process same event second time (idempotency guard)
    res2 = engine.process_event(ev0)
    assert res2.get("duplicate_ignored") is True
    assert engine.total_stream_minutes == ev0.stream_minutes
    assert len(engine.events) == 1

