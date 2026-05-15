"""Supabase Storage I/O for the ingestion-files bucket."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin

BUCKET = "ingestion-files"


async def upload_original(
    *,
    tenant_id: UUID,
    job_id: UUID,
    file_id: UUID,
    filename: str,
    content: bytes,
    mime_type: str,
) -> str:
    """Upload an original file, return the storage path."""
    path = f"{tenant_id}/{job_id}/{file_id}/{filename}"
    sb = get_supabase_admin()

    def _up():
        sb.storage.from_(BUCKET).upload(
            path=path,
            file=content,
            file_options={"content-type": mime_type, "upsert": "false"},
        )

    await asyncio.to_thread(_up)
    return path


async def download_original(path: str) -> bytes:
    sb = get_supabase_admin()

    def _dl():
        return sb.storage.from_(BUCKET).download(path)

    return await asyncio.to_thread(_dl)


async def create_signed_url(path: str, *, expires_in_seconds: int = 60) -> str:
    """Time-limited public URL for the review UI's file viewer."""
    sb = get_supabase_admin()

    def _sign():
        res: dict[str, Any] = sb.storage.from_(BUCKET).create_signed_url(
            path, expires_in_seconds
        )
        return res["signedURL"]

    return await asyncio.to_thread(_sign)
