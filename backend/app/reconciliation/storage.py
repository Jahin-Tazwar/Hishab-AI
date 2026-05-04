"""Supabase Storage helpers for reconciliation file downloads."""
from __future__ import annotations

import asyncio

from app.core.exceptions import StorageDownloadFailedError
from app.database import get_supabase_admin


async def download_xlsx(bucket: str, path: str) -> bytes:
    """Download a file from Supabase Storage as bytes (service-role)."""
    supabase = get_supabase_admin()

    def _call() -> bytes:
        return supabase.storage.from_(bucket).download(path)

    try:
        return await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001 — re-raise typed
        raise StorageDownloadFailedError(path=path, reason=str(exc)) from exc
