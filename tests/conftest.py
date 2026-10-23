"""Shared test setup.

DEMO_KEY has no default in source, so tests supply their own throwaway key.
"""

import pytest

from residual_live.config import settings

TEST_DEMO_KEY = "test-only-demo-key"


@pytest.fixture(autouse=True)
def demo_key(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_KEY", TEST_DEMO_KEY)
    return TEST_DEMO_KEY
