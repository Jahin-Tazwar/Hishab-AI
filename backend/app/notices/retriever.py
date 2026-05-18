"""Retrieve citation chunks for a notice + reconciliation pair.

Builds a natural-language query combining the notice's allegation language
and the reconciliation's actual numbers, embeds it, and runs ANN against
citation_corpus_chunks pre-filtered by topic_tags.
"""
from __future__ import annotations

from typing import List

from app.notices.llm import NoticeLLMAdapter
from app.notices.persistence import retrieve_citation_chunks
from app.notices.schemas import CitationChunk, ParsedNotice, ReconSummary


_K = 8                                # how many chunk groups to surface
_TOPIC_TAGS = ["itc", "mismatch", "documentary_evidence", "denial_grounds"]


def build_query_text(parsed: ParsedNotice, summary: ReconSummary) -> str:
    """Single dense paragraph capturing both the notice and our position."""
    parts: list[str] = [
        f"NBR notice category: {parsed.notice_type.value}.",
    ]
    if parsed.alleged_shortfall_bdt is not None:
        parts.append(
            f"NBR alleges input VAT shortfall of {parsed.alleged_shortfall_bdt} BDT, "
            f"claiming taxpayer over-claimed ITC."
        )
    if parsed.alleged_itc_claimed_bdt and parsed.alleged_itc_allowed_bdt:
        parts.append(
            f"NBR figures: claimed {parsed.alleged_itc_claimed_bdt} BDT, "
            f"allowed {parsed.alleged_itc_allowed_bdt} BDT."
        )
    parts.append(
        f"Reconciled position: safe ITC {summary.safe_itc_bdt} BDT, "
        f"at-risk ITC {summary.at_risk_itc_bdt} BDT, "
        f"total VAT claimed {summary.total_vat_claimed_bdt} BDT."
    )
    parts.append(
        f"Match counts: exact={summary.matched_exact}, fuzzy={summary.matched_fuzzy}, "
        f"partial={summary.partial_match}, no_match={summary.no_match}."
    )
    parts.append(
        "Relevant law: input tax credit eligibility, documentary evidence "
        "requirements (Mushak 6.3), denial grounds for ITC, mismatch "
        "reconciliation procedure."
    )
    return " ".join(parts)


async def retrieve(
    parsed: ParsedNotice,
    summary: ReconSummary,
    *,
    adapter: NoticeLLMAdapter,
    k: int = _K,
    topic_tags: list[str] | None = None,
) -> List[CitationChunk]:
    query = build_query_text(parsed, summary)
    embedding = adapter.embed_query(query)
    chunks = await retrieve_citation_chunks(
        embedding=embedding,
        topic_tags=topic_tags or _TOPIC_TAGS,
        k=k,
    )
    return chunks
