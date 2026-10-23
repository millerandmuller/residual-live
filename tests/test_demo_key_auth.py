"""Demo key auth must fail closed when DEMO_KEY is not configured."""

from fastapi.testclient import TestClient

from residual_live.app import app
from residual_live.config import settings


def test_mutating_endpoint_refused_when_demo_key_unset(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_KEY", "")
    client = TestClient(app)

    res_no_header = client.post("/api/demo/reset")
    res_any_header = client.post("/api/demo/reset", headers={"X-Demo-Key": "anything"})

    assert res_no_header.status_code == 503
    assert res_any_header.status_code == 503


def test_wrong_key_rejected_and_right_key_accepted(demo_key):
    client = TestClient(app)

    assert client.post("/api/demo/reset", headers={"X-Demo-Key": "wrong"}).status_code == 401
    assert client.post("/api/demo/reset", headers={"X-Demo-Key": demo_key}).status_code != 401
