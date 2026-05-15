"""Engine for XLSX/CSV with the existing canonical column headers.

This is a thin wrapper that delegates to the existing reconciliation parser
so behavior is bit-identical to today's flow.
"""
from __future__ import annotations

import io
from typing import cast

import pandas as pd

from app.ingestion.engines.base import ExtractedFileResult, ExtractionContext
from app.ingestion.schemas import ExtractedRowData, JobKind
from app.reconciliation.parser import (
    _PURCHASE_COLUMNS,
    _SUPPLIER_COLUMNS,
    parse_purchase_register,
    parse_supplier_export,
)


def _canonical_set(kind: JobKind) -> set[str]:
    cols = _PURCHASE_COLUMNS if kind == JobKind.PURCHASE_REGISTER else _SUPPLIER_COLUMNS
    return set(cols.keys())  # already lowercased keys


class PandasCanonicalEngine:
    name = "pandas"

    def handles_headers(self, headers: list[str], kind: JobKind) -> bool:
        norm = {(h or "").strip().lower() for h in headers}
        return _canonical_set(kind).issubset(norm)

    def extract(
        self, file_bytes: bytes, ctx: ExtractionContext
    ) -> ExtractedFileResult:
        if ctx.kind == JobKind.PURCHASE_REGISTER:
            parsed = parse_purchase_register(file_bytes)
        else:
            parsed = parse_supplier_export(file_bytes)

        rows: list[ExtractedRowData] = []
        for r in parsed:
            d = r.model_dump()
            rows.append(ExtractedRowData(**d))

        return ExtractedFileResult(
            rows=rows,
            needs_review=False,
            extraction_engine="pandas",
            page_count=1,
            warnings=[],
        )

    @staticmethod
    def headers_from_bytes(file_bytes: bytes) -> list[str]:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl", nrows=0)
        return [str(c) for c in df.columns]
