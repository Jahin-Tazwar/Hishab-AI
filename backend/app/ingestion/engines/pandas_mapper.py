"""Engine for XLSX/CSV with NON-canonical headers.

Uses the LLM column-mapper to learn a (canonical_field -> source_column)
mapping, applies it, then runs the parser on the rewritten DataFrame.

Mapping is cached in `ingestion_column_mappings` per (tenant, kind,
header_signature). Cache hit → zero LLM cost; cache miss → one Gemini Flash
call. The mapping for a brand-new header signature is also surfaced to the
review UI for user confirmation (see Task 21).

Cache I/O is injected via `mapping_cache_get` / `mapping_cache_put` at
construction time so tests can supply no-op lambdas; the default
implementations call `asyncio.run(persistence.{get_cached_mapping,upsert_mapping})`.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Optional
from uuid import UUID

import pandas as pd

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.llm import column_signature, get_llm_adapter
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.ingestion import persistence as p

_CANONICAL = (
    "invoice_no", "supplier_bin", "supplier_name", "buyer_bin",
    "invoice_date", "taxable_amount_bdt", "vat_amount_bdt",
)


def _coerce_date(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    return value  # let pydantic raise if unparseable


class PandasMapperEngine:
    name = "pandas+llm-mapper"

    def __init__(
        self,
        *,
        mapping_cache_get: Optional[Callable[..., Optional[dict]]] = None,
        mapping_cache_put: Optional[Callable[..., None]] = None,
    ) -> None:
        self._cache_get = mapping_cache_get or self._default_cache_get
        self._cache_put = mapping_cache_put or self._default_cache_put

    @staticmethod
    def _default_cache_get(*, tenant_id, kind, header_signature):
        return asyncio.run(p.get_cached_mapping(
            tenant_id=tenant_id, kind=kind, header_signature=header_signature,
        ))

    @staticmethod
    def _default_cache_put(*, tenant_id, kind, header_signature, mapping):
        asyncio.run(p.upsert_mapping(
            tenant_id=tenant_id, kind=kind,
            header_signature=header_signature, mapping=mapping,
        ))

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        headers = [str(c) for c in df.columns]
        sig = column_signature(headers)
        tenant_uuid = UUID(ctx.tenant_id)

        cached = self._cache_get(
            tenant_id=tenant_uuid, kind=ctx.kind, header_signature=sig,
        )

        if cached is None:
            sample_rows = df.head(3).fillna("").astype(str).values.tolist()
            mapping = get_llm_adapter().map_columns(
                headers=headers, sample_rows=sample_rows, kind=ctx.kind,
            )
            self._cache_put(
                tenant_id=tenant_uuid, kind=ctx.kind,
                header_signature=sig, mapping=mapping,
            )
        else:
            mapping = cached

        rows: list[ExtractedRowData] = []
        for _, src in df.iterrows():
            rec: dict[str, Any] = {}
            for canonical_field in _CANONICAL:
                src_col = mapping.get(canonical_field)
                if src_col is None or src_col not in df.columns:
                    continue
                val = src[src_col]
                if pd.isna(val):
                    continue
                if canonical_field == "invoice_date":
                    rec[canonical_field] = _coerce_date(val)
                elif canonical_field in ("taxable_amount_bdt", "vat_amount_bdt"):
                    rec[canonical_field] = Decimal(str(val))
                else:
                    rec[canonical_field] = str(val).strip() or None
            required = {"invoice_no", "invoice_date",
                        "taxable_amount_bdt", "vat_amount_bdt"}
            if not required.issubset(rec.keys()):
                continue
            rows.append(ExtractedRowData(**rec))

        return ExtractedFileResult(
            rows=rows,
            needs_review=False,
            extraction_engine="pandas+llm-mapper",
            page_count=1,
            warnings=[],
        )
