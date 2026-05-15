"""Shared fixtures for ingestion tests."""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest

# Integration tests are gated on a real Supabase URL being present.
pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="INGESTION_TEST_SUPABASE_URL not set; persistence tests require a live DB",
)


@pytest.fixture
def tenant_id() -> UUID:
    raw = os.environ.get("INGESTION_TEST_TENANT_ID")
    if raw:
        return UUID(raw)
    pytest.skip("INGESTION_TEST_TENANT_ID required")


@pytest.fixture
def client_id() -> UUID:
    raw = os.environ.get("INGESTION_TEST_CLIENT_ID")
    if raw:
        return UUID(raw)
    pytest.skip("INGESTION_TEST_CLIENT_ID required")


@pytest.fixture
def user_id() -> UUID:
    raw = os.environ.get("INGESTION_TEST_USER_ID")
    if raw:
        return UUID(raw)
    pytest.skip("INGESTION_TEST_USER_ID required")
