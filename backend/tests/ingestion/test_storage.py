"""Storage module tests (gated on real Supabase Storage)."""
from uuid import uuid4

import pytest

from app.ingestion import storage as s


@pytest.mark.asyncio
async def test_upload_then_download_roundtrip(tenant_id):
    job_id = uuid4()
    file_id = uuid4()
    payload = b"hello-world-" + str(uuid4()).encode()
    path = await s.upload_original(
        tenant_id=tenant_id,
        job_id=job_id,
        file_id=file_id,
        filename="test.bin",
        content=payload,
        mime_type="application/octet-stream",
    )
    assert path.startswith(f"{tenant_id}/{job_id}/{file_id}/")
    got = await s.download_original(path)
    assert got == payload


@pytest.mark.asyncio
async def test_signed_url_returns_string(tenant_id):
    job_id = uuid4()
    file_id = uuid4()
    path = await s.upload_original(
        tenant_id=tenant_id, job_id=job_id, file_id=file_id,
        filename="x.txt", content=b"x", mime_type="text/plain",
    )
    url = await s.create_signed_url(path, expires_in_seconds=60)
    assert isinstance(url, str) and url.startswith("http")
