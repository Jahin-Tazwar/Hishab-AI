"""Live-DB seed-script tests. Gated like other live tests."""
import os
import pathlib

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("INGESTION_TEST_SUPABASE_URL"),
    reason="Seed test requires live Supabase",
)


def test_seed_corpus_idempotent(monkeypatch):
    """Running the seeder twice must not duplicate rows."""
    from scripts.seed_citation_corpus import seed_corpus
    from app.database import get_supabase_admin

    sb = get_supabase_admin()
    n1 = seed_corpus()
    n2 = seed_corpus()
    assert n1 == n2, f"second run upserted a different count: {n1} vs {n2}"

    corpus_dir = pathlib.Path(__file__).parents[2] / "app" / "notices" / "corpus"
    expected = sum(
        1 for p in corpus_dir.glob("*.md")
        if p.name not in ("README.md", "corpus_review.md")
    )
    res = sb.table("citation_corpus_chunks").select("id", count="exact").execute()
    assert res.count == expected
