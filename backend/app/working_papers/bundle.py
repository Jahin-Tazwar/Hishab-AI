"""Pure evidence-bundle ZIP builder. Storage I/O is injected as `download`
so this is testable without Supabase."""
from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Callable

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


class EvidenceBundleTooLargeError(Exception):
    pass


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "file")


def build_evidence_zip(
    *,
    binder_docx: bytes,
    evidence: list[dict[str, Any]],
    download: Callable[[str, str], bytes],
    reference: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> bytes:
    """Assemble a ZIP: 00_binder.docx + E-0N_<file> per available evidence +
    MANIFEST.txt. Missing files are recorded in the manifest, not fatal.
    Raises EvidenceBundleTooLargeError if cumulative bytes exceed max_bytes."""
    total = len(binder_docx)
    manifest_lines = [f"Audit Defense Pack evidence bundle — {reference}", ""]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("00_binder.docx", binder_docx)
        for e in evidence:
            ref, fname = e["ref"], e.get("filename") or "file"
            try:
                blob = download(e["bucket"], e["storage_path"])
            except Exception as exc:  # noqa: BLE001 — report, don't fail the bundle
                manifest_lines.append(f"{ref}  {fname}  [{e.get('source_type')}]  MISSING ({exc})")
                continue
            total += len(blob)
            if total > max_bytes:
                raise EvidenceBundleTooLargeError(
                    f"Evidence bundle exceeds {max_bytes} bytes")
            z.writestr(f"{ref}_{_safe(fname)}", blob)
            manifest_lines.append(f"{ref}  {fname}  [{e.get('source_type')}]  included")
        z.writestr("MANIFEST.txt", "\n".join(manifest_lines) + "\n")
    return buf.getvalue()
