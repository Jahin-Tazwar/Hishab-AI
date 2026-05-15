"""Pure-logic token bucket tests — no DB."""
from uuid import uuid4

import pytest

from app.ingestion.rate_limit import TokenBucketRegistry, RateLimitExceeded


def test_first_call_passes():
    reg = TokenBucketRegistry(per_min=2, per_day=100)
    t = uuid4()
    reg.acquire(t)


def test_third_call_in_minute_blocks():
    reg = TokenBucketRegistry(per_min=2, per_day=100)
    t = uuid4()
    reg.acquire(t); reg.acquire(t)
    with pytest.raises(RateLimitExceeded):
        reg.acquire(t)


def test_separate_tenants_dont_share():
    reg = TokenBucketRegistry(per_min=1, per_day=100)
    a, b = uuid4(), uuid4()
    reg.acquire(a)
    reg.acquire(b)  # b has its own bucket
