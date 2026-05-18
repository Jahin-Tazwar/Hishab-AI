"""Seed (or re-seed) the citation_corpus_chunks table from markdown files.

Reads every `app/notices/corpus/*.md` (skipping README.md and
corpus_review.md), parses the YAML front-matter, computes a 768-dim
embedding via Gemini text-embedding-004, and upserts on
(source, source_ref, subsection, language).

Idempotent: re-running updates embeddings + body if changed but doesn't
duplicate rows.

Run: cd backend && python -m scripts.seed_citation_corpus
"""
from __future__ import annotations

import os
import pathlib
import sys

import yaml
from dotenv import load_dotenv

load_dotenv()

CORPUS_DIR = pathlib.Path(__file__).parents[1] / "app" / "notices" / "corpus"
_NON_CLAUSE_FILES = {"README.md", "corpus_review.md"}


def _embed(client, text: str) -> list[float]:
    res = client.models.embed_content(
        model="text-embedding-004",
        contents=text,
    )
    # google-genai returns a list of Embedding objects; we always send one input
    return list(res.embeddings[0].values)


def seed_corpus() -> int:
    """Upsert every corpus file. Returns the number of rows written."""
    from google import genai
    from app.database import get_supabase_admin

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY required to seed corpus")

    client = genai.Client(api_key=api_key)
    sb = get_supabase_admin()

    n = 0
    for path in sorted(CORPUS_DIR.glob("*.md")):
        if path.name in _NON_CLAUSE_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        if len(parts) < 3:
            print(f"SKIP {path.name}: no front-matter", file=sys.stderr)
            continue
        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()

        embedding = _embed(client, f"{meta['title']}\n\n{body}")

        sb.table("citation_corpus_chunks").upsert({
            "source":     meta["source"],
            "source_ref": meta["source_ref"],
            "subsection": meta.get("subsection") or None,
            "language":   meta["language"],
            "title":      meta["title"],
            "body":       body,
            "topic_tags": list(meta.get("topic_tags") or []),
            "embedding":  embedding,
        }, on_conflict="source,source_ref,subsection,language").execute()
        n += 1
        print(f"  upserted {path.name}")
    return n


if __name__ == "__main__":
    count = seed_corpus()
    print(f"Done: {count} chunks seeded.")
