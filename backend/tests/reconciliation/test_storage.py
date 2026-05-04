"""Tests for the storage download helper."""
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import StorageDownloadFailedError
from app.reconciliation.storage import download_xlsx


@pytest.mark.asyncio
async def test_download_xlsx_returns_bytes(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.storage.from_.return_value.download.return_value = b"fake-xlsx-bytes"

    monkeypatch.setattr(
        "app.reconciliation.storage.get_supabase_admin",
        lambda: fake_supabase,
    )

    result = await download_xlsx("recon-files", "tenant/client/recon/file.xlsx")
    assert result == b"fake-xlsx-bytes"
    fake_supabase.storage.from_.assert_called_once_with("recon-files")
    fake_supabase.storage.from_.return_value.download.assert_called_once_with(
        "tenant/client/recon/file.xlsx"
    )


@pytest.mark.asyncio
async def test_download_xlsx_raises_on_error(monkeypatch):
    fake_supabase = MagicMock()
    fake_supabase.storage.from_.return_value.download.side_effect = Exception("404 not found")

    monkeypatch.setattr(
        "app.reconciliation.storage.get_supabase_admin",
        lambda: fake_supabase,
    )

    with pytest.raises(StorageDownloadFailedError) as ei:
        await download_xlsx("recon-files", "missing/file.xlsx")
    assert "missing/file.xlsx" in ei.value.message
    assert "404 not found" in ei.value.details["reason"]
