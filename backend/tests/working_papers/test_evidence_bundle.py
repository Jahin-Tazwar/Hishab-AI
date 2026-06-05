"""Tests for the evidence-bundle ZIP builder."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.working_papers.bundle import build_evidence_zip, EvidenceBundleTooLargeError


def test_build_zip_includes_binder_present_and_missing():
    evidence = [
        {"ref": "E-01", "filename": "pr.xlsx", "source_type": "purchase_register",
         "bucket": "recon-files", "storage_path": "t/c/pr.xlsx"},
        {"ref": "E-02", "filename": "notice.pdf", "source_type": "nbr_notice",
         "bucket": "notices", "storage_path": "t/c/missing.pdf"},
    ]

    def fake_download(bucket, path):
        if path == "t/c/pr.xlsx":
            return b"PR-BYTES"
        raise FileNotFoundError("not found")

    data = build_evidence_zip(
        binder_docx=b"DOCX-BYTES", evidence=evidence,
        download=fake_download, reference="WP-X")
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    assert "00_binder.docx" in names
    assert "E-01_pr.xlsx" in names
    assert "MANIFEST.txt" in names
    manifest = z.read("MANIFEST.txt").decode()
    assert "E-01" in manifest and "included" in manifest
    assert "E-02" in manifest and "MISSING" in manifest
    assert not any(name.startswith("E-02_") for name in names)


def test_build_zip_enforces_size_cap():
    evidence = [{"ref": "E-01", "filename": "big.bin", "source_type": "x",
                 "bucket": "recon-files", "storage_path": "t/c/big.bin"}]

    def fake_download(bucket, path):
        return b"x" * (60 * 1024 * 1024)  # 60 MB

    with pytest.raises(EvidenceBundleTooLargeError):
        build_evidence_zip(binder_docx=b"D", evidence=evidence,
                           download=fake_download, reference="WP-X",
                           max_bytes=50 * 1024 * 1024)
