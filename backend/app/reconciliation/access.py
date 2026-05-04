"""Defense-in-depth document access checks for the reconciliation flow."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from app.core.exceptions import DocumentNotFoundError, DocumentTenantMismatchError
from app.database import get_supabase_admin


@dataclass(frozen=True)
class DocumentPaths:
    pr_path: str
    sf_path: str


async def fetch_and_validate_documents(
    *,
    pr_doc_id: UUID,
    sf_doc_id: UUID,
    tenant_id: UUID,
    client_id: UUID,
) -> DocumentPaths:
    """Confirm both docs exist, belong to the tenant, and reference the same client."""
    supabase = get_supabase_admin()

    def _query():
        return (
            supabase.table("documents")
            .select("id,tenant_id,client_id,storage_path,doc_type")
            .in_("id", [str(pr_doc_id), str(sf_doc_id)])
            .execute()
        )

    result = await asyncio.to_thread(_query)
    rows = result.data or []
    by_id = {row["id"]: row for row in rows}

    pr = by_id.get(str(pr_doc_id))
    sf = by_id.get(str(sf_doc_id))

    if pr is None:
        raise DocumentNotFoundError(doc_id=str(pr_doc_id))
    if sf is None:
        raise DocumentNotFoundError(doc_id=str(sf_doc_id))

    for row in (pr, sf):
        if row["tenant_id"] != str(tenant_id):
            raise DocumentTenantMismatchError(document_id=row["id"])
        if row["client_id"] != str(client_id):
            raise DocumentTenantMismatchError(document_id=row["id"])

    return DocumentPaths(pr_path=pr["storage_path"], sf_path=sf["storage_path"])
