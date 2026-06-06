"""Audit Defense Pack recipe — composes a per-notice rebuttal binder.

Anchored on a notice_id. Derives the linked reconciliation, reuses the
At-Risk ITC recipe for the reconciled-position section (so numbers tie out),
builds the CA override log, pulls the drafted reply, and indexes the linked
evidence artifacts (recon source files + the notice file).
"""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin
from app.working_papers.recipes.at_risk_itc import AtRiskItcScheduleRecipe

_PAGE = 1000


class AuditDefensePackRecipe:
    id: str = "audit_defense_pack"
    version: str = "v1"

    async def compose(self, *, tenant_id: UUID, notice_id: UUID, **_: Any) -> dict[str, Any]:
        sb = get_supabase_admin()

        def _q_notice():
            return (sb.table("notices").select("*")
                    .eq("id", str(notice_id)).eq("tenant_id", str(tenant_id))
                    .single().execute())

        notice = (await asyncio.to_thread(_q_notice)).data

        def _q_client(cid):
            return (sb.table("clients").select("id, name, bin, tin")
                    .eq("id", cid).eq("tenant_id", str(tenant_id))
                    .single().execute())

        client = (await asyncio.to_thread(_q_client, notice["client_id"])).data

        recon_id = notice.get("linked_reconciliation_id")
        reconciled_position = None
        override_log: list[dict[str, Any]] = []
        evidence_index: list[dict[str, Any]] = []
        seq = 0

        def _ref():
            nonlocal seq
            seq += 1
            return f"E-{seq:02d}"

        if recon_id:
            reconciled_position = await AtRiskItcScheduleRecipe().compose(
                tenant_id=tenant_id, reconciliation_id=UUID(str(recon_id)))

            def _q_recon():
                return (sb.table("vat_reconciliations")
                        .select("purchase_register_doc_id, supplier_data_doc_id")
                        .eq("id", str(recon_id)).eq("tenant_id", str(tenant_id))
                        .single().execute())

            recon = (await asyncio.to_thread(_q_recon)).data

            # Override log: only lines where the CA recorded a decision.
            def _q_overrides(offset, limit):
                return (sb.table("recon_line_items")
                        .select("pr_supplier_name, pr_supplier_bin, pr_invoice_no, "
                                "ca_override, ca_notes")
                        .eq("tenant_id", str(tenant_id))
                        .eq("reconciliation_id", str(recon_id))
                        .order("pr_supplier_name")
                        .range(offset, offset + limit - 1).execute())

            rows: list[dict] = []
            while True:
                batch = (await asyncio.to_thread(_q_overrides, len(rows), _PAGE)).data or []
                rows.extend(batch)
                if len(batch) < _PAGE:
                    break
            for r in rows:
                if r.get("ca_override"):
                    override_log.append({
                        "supplier_name": r.get("pr_supplier_name"),
                        "supplier_bin": r.get("pr_supplier_bin"),
                        "invoice_no": r.get("pr_invoice_no"),
                        "ca_override": r.get("ca_override"),
                        "ca_notes": r.get("ca_notes"),
                    })

            # Evidence: recon source files (bucket recon-files).
            for col, kind in (("purchase_register_doc_id", "purchase_register"),
                              ("supplier_data_doc_id", "supplier_export")):
                did = recon.get(col)
                if not did:
                    continue

                def _q_doc(d=did):
                    return (sb.table("documents")
                            .select("id, original_filename, storage_path, doc_type")
                            .eq("id", str(d)).eq("tenant_id", str(tenant_id))
                            .is_("deleted_at", "null")
                            .execute())

                result = (await asyncio.to_thread(_q_doc)).data
                # Result may be a list (PostgREST) or a single dict; normalise.
                if isinstance(result, list):
                    doc = result[0] if result else None
                else:
                    doc = result
                if doc:
                    evidence_index.append({
                        "ref": _ref(), "document_id": doc["id"],
                        "filename": doc.get("original_filename") or "document",
                        "source_type": kind, "bucket": "recon-files",
                        "storage_path": doc["storage_path"],
                    })

        # Drafted reply: finalized if present, else most recently updated.
        def _q_drafts():
            return (sb.table("notice_drafts")
                    .select("language, status, body_html, citations, "
                            "finalized_at, updated_at")
                    .eq("notice_id", str(notice_id)).eq("tenant_id", str(tenant_id))
                    .order("updated_at", desc=True).execute())

        drafts = (await asyncio.to_thread(_q_drafts)).data or []
        drafted_reply = None
        if drafts:
            chosen = next((d for d in drafts if d.get("status") == "finalized"), drafts[0])
            drafted_reply = {
                "language": chosen.get("language"),
                "status": chosen.get("status"),
                "body_html": chosen.get("body_html") or "",
                "citations": list(chosen.get("citations") or []),
            }

        # Evidence: the notice file itself (bucket notices).
        if notice.get("storage_path"):
            evidence_index.append({
                "ref": _ref(), "document_id": None,
                "filename": notice.get("original_filename") or "notice.pdf",
                "source_type": "nbr_notice", "bucket": "notices",
                "storage_path": notice["storage_path"],
            })

        return {
            "kind": self.id,
            "recipe_version": self.version,
            "client_id": client["id"],
            "client_name": client["name"],
            "client_bin": client.get("bin"),
            "client_tin": client.get("tin"),
            "notice_id": str(notice_id),
            "notice": {
                "notice_no": notice.get("notice_no"),
                "notice_date": notice.get("notice_date"),
                "notice_type": notice.get("notice_type"),
                "period_start": notice.get("period_start"),
                "period_end": notice.get("period_end"),
                "taxpayer_bin": notice.get("taxpayer_bin"),
                "taxpayer_tin": notice.get("taxpayer_tin"),
                "alleged_itc_claimed_bdt": notice.get("alleged_itc_claimed_bdt"),
                "alleged_itc_allowed_bdt": notice.get("alleged_itc_allowed_bdt"),
                "alleged_shortfall_bdt": notice.get("alleged_shortfall_bdt"),
            },
            "reconciliation_id": str(recon_id) if recon_id else None,
            "reconciled_position": reconciled_position,
            "override_log": override_log,
            "drafted_reply": drafted_reply,
            "evidence_index": evidence_index,
        }
