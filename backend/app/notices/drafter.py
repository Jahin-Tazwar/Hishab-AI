"""Notice drafter — LLM call + post-processing.

Builds the prompt, calls the adapter, validates that every [CIT-N] tag
emitted by the model resolves to a real retrieved chunk, sanitizes the
resulting HTML, and returns the persisted-ready shape.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any

import bleach

from app.notices.llm import NoticeLLMAdapter
from app.notices.schemas import (
    CitationChunk, DraftReply, ParsedNotice, ReconSummary,
)


_HTML_ALLOWED_TAGS = ["p", "strong", "em", "br", "sup"]
_HTML_ALLOWED_ATTRS = {"sup": ["class", "data-ref"]}
_CITATION_TAG_RE = re.compile(r"\[CIT-(\d+)\]")
_PLACEHOLDER = "[citation needed — review]"


def build_draft_prompt(
    parsed: ParsedNotice,
    summary: ReconSummary,
    citations: list[CitationChunk],
) -> str:
    """Assemble the user-side prompt sent to Gemini.

    System instruction lives in app/notices/llm.py (_DRAFT_SYSTEM); this
    function only assembles the per-notice content.
    """
    groups: list[tuple[str, list[CitationChunk]]] = []
    seen: dict[tuple[str, str, str | None], int] = {}
    for c in citations:
        key = (c.source, c.source_ref, c.subsection)
        if key not in seen:
            seen[key] = len(groups)
            groups.append((c.source_ref, [c]))
        else:
            groups[seen[key]][1].append(c)

    cit_lines = []
    for i, (_ref, items) in enumerate(groups, start=1):
        for item in items:
            tag = f"[CIT-{i}]"
            cit_lines.append(
                f"{tag} ({item.language}) {item.source_ref}"
                + (f" {item.subsection}" if item.subsection else "")
                + f": {item.body[:600]}"
            )

    parts = [
        "## NOTICE METADATA",
        f"Notice no: {parsed.notice_no or '(unknown)'}",
        f"Notice date: {parsed.notice_date or '(unknown)'}",
        f"Taxpayer BIN: {parsed.taxpayer_bin or '(unknown)'}",
        f"Period: {parsed.period_start} to {parsed.period_end}",
        f"Alleged claimed ITC: {parsed.alleged_itc_claimed_bdt} BDT",
        f"Alleged allowed ITC: {parsed.alleged_itc_allowed_bdt} BDT",
        f"Alleged shortfall: {parsed.alleged_shortfall_bdt} BDT",
        "",
        "## RECONCILIATION POSITION (ground truth)",
        f"Safe ITC: {summary.safe_itc_bdt} BDT",
        f"At-risk ITC: {summary.at_risk_itc_bdt} BDT",
        f"Total VAT claimed: {summary.total_vat_claimed_bdt} BDT",
        f"Match counts — exact: {summary.matched_exact}, fuzzy: {summary.matched_fuzzy}, "
        f"partial: {summary.partial_match}, no_match: {summary.no_match}",
    ]
    if summary.disputed_rows:
        parts.append("Disputed rows (representative sample):")
        for r in summary.disputed_rows[:20]:
            parts.append(
                f"  - {r.get('supplier_name','?')} (BIN {r.get('supplier_bin','?')}) "
                f"inv {r.get('invoice_no','?')} VAT {r.get('vat_amount_bdt','?')} "
                f"[{r.get('match_status','?')}]"
            )

    parts += [
        "",
        "## CITATIONS YOU MAY CITE",
        "Reference each by its tag, e.g. [CIT-1]. Cite ONLY from this list.",
        *cit_lines,
        "",
        "## TASK",
        "Draft a formal Bangla reply letter following NBR conventions. ",
        "Return a JSON object matching the response schema with body_paragraphs, ",
        "computation_table_rows (in English, suitable for an appendix), and ",
        "cited_refs (the [CIT-N] tags you used). The body must explain the ",
        "taxpayer's actual reconciled position and cite supporting law.",
    ]
    return "\n".join(parts)


def _validate_citation_tags(text: str, *, allowed_tags: set[str]) -> str:
    """Replace any [CIT-N] not in `allowed_tags` with the review placeholder."""
    def _sub(m: re.Match[str]) -> str:
        tag = f"CIT-{m.group(1)}"
        return f"[{tag}]" if tag in allowed_tags else _PLACEHOLDER
    return _CITATION_TAG_RE.sub(_sub, text)


def _paragraph_to_html(
    text: str,
    *,
    allowed_tags: set[str],
    tag_to_ref: dict[str, str],
) -> str:
    """Render one paragraph: validate cites, convert [CIT-N] → <sup>, sanitize."""
    safe = _validate_citation_tags(text, allowed_tags=allowed_tags)

    def _to_sup(m: re.Match[str]) -> str:
        tag = f"CIT-{m.group(1)}"
        if tag in tag_to_ref:
            return f'<sup class="citation" data-ref="{tag}">[{m.group(1)}]</sup>'
        return _PLACEHOLDER

    with_sups = _CITATION_TAG_RE.sub(_to_sup, safe)
    sanitized = bleach.clean(
        with_sups,
        tags=_HTML_ALLOWED_TAGS,
        attributes=_HTML_ALLOWED_ATTRS,
        strip=True,
    )
    return f"<p>{sanitized}</p>"


def finalize_draft_output(
    raw: DraftReply,
    *,
    retrieved_chunks: list[CitationChunk],
) -> dict[str, Any]:
    """Post-process raw LLM output into persisted-ready shape.

    Returns dict with keys: body_html (str), appendix_json (dict),
    citations (list[dict]).
    """
    groups: list[tuple[str, list[CitationChunk]]] = []
    seen: dict[tuple[str, str, str | None], int] = {}
    for c in retrieved_chunks:
        key = (c.source, c.source_ref, c.subsection)
        if key not in seen:
            seen[key] = len(groups)
            groups.append((c.source_ref, [c]))
        else:
            groups[seen[key]][1].append(c)

    tag_to_ref: dict[str, str] = {}
    tag_to_chunk: dict[str, CitationChunk] = {}
    for i, (_ref, items) in enumerate(groups, start=1):
        tag = f"CIT-{i}"
        tag_to_ref[tag] = items[0].source_ref
        bn = next((c for c in items if c.language == "bn"), items[0])
        tag_to_chunk[tag] = bn

    allowed_tags = set(tag_to_ref.keys())

    paragraph_htmls: list[str] = []
    citations: list[dict[str, Any]] = []
    seen_tag_in_para: set[tuple[str, int]] = set()
    for idx, para in enumerate(raw.body_paragraphs):
        para_html = _paragraph_to_html(
            para.text, allowed_tags=allowed_tags, tag_to_ref=tag_to_ref,
        )
        paragraph_htmls.append(para_html)
        for m in _CITATION_TAG_RE.finditer(para.text):
            tag = f"CIT-{m.group(1)}"
            if tag in tag_to_chunk and (tag, idx) not in seen_tag_in_para:
                chunk = tag_to_chunk[tag]
                citations.append({
                    "corpus_chunk_id": str(chunk.id),
                    "source_ref": chunk.source_ref,
                    "snippet": chunk.body[:240],
                    "paragraph_idx": idx,
                })
                seen_tag_in_para.add((tag, idx))

    body_html = "\n".join(paragraph_htmls)

    appendix_json: dict[str, Any] = {
        "rows": [r.model_dump(mode="json") for r in raw.computation_table_rows],
    }

    return {
        "body_html": body_html,
        "appendix_json": appendix_json,
        "citations": citations,
    }


async def draft(
    parsed: ParsedNotice,
    summary: ReconSummary,
    citations: list[CitationChunk],
    *,
    adapter: NoticeLLMAdapter,
    lookup_key_override: str | None = None,
) -> dict[str, Any]:
    """Run the LLM call and return the finalized draft shape."""
    prompt = build_draft_prompt(parsed, summary, citations)
    lookup_key = lookup_key_override or hashlib.sha256(prompt.encode()).hexdigest()[:16]
    # adapter.draft_reply is sync (Gemini call); off-thread to keep the
    # event loop responsive during the multi-second LLM round-trip.
    raw = await asyncio.to_thread(
        adapter.draft_reply, prompt=prompt, lookup_key=lookup_key,
    )
    return finalize_draft_output(raw, retrieved_chunks=citations)
