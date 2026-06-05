"""At-Risk ITC Schedule recipe — composes the client-facing deliverable
from a reconciliation_id.

Pulls the recon header + lines via persistence helpers. Groups by supplier.
Computes per-supplier totals. Tags each line with a recommended action.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin


class AtRiskItcScheduleRecipe:
    id: str = "at_risk_itc_schedule"
    version: str = "v1"

    async def compose(
        self,
        *,
        tenant_id: UUID,
        reconciliation_id: UUID,
        **_: Any,
    ) -> dict[str, Any]:
        sb = get_supabase_admin()

        def _q_recon():
            return (
                sb.table("vat_reconciliations")
                .select("*")
                .eq("id", str(reconciliation_id))
                .eq("tenant_id", str(tenant_id))
                .single()
                .execute()
            )

        def _q_client(cid: str):
            return (
                sb.table("clients")
                .select("id, name, bin")
                .eq("id", cid)
                .eq("tenant_id", str(tenant_id))
                .single()
                .execute()
            )

        def _q_lines():
            return (
                sb.table("recon_line_items")
                .select(
                    "id, pr_invoice_no, pr_supplier_bin, pr_supplier_name, "
                    "pr_invoice_date, pr_taxable_amount_bdt, pr_vat_amount_bdt, "
                    "match_status, match_score, ca_override, ca_notes"
                )
                .eq("tenant_id", str(tenant_id))
                .eq("reconciliation_id", str(reconciliation_id))
                .order("pr_supplier_name")
                .order("pr_invoice_date")
                .execute()
            )

        recon = (await asyncio.to_thread(_q_recon)).data
        client = (await asyncio.to_thread(_q_client, recon["client_id"])).data
        rows = (await asyncio.to_thread(_q_lines)).data or []

        # Filter to at-risk lines: anything not exact, OR exact but the CA disputed/ignored.
        # `exact` matches with no CA override = safe; everything else lands here.
        at_risk_rows = [
            r for r in rows
            if r["match_status"] != "exact" or r.get("ca_override") in ("disputed", "ignore")
        ]

        # Group by (supplier_bin, supplier_name)
        groups: dict[tuple[str | None, str | None], list[dict]] = {}
        for r in at_risk_rows:
            key = (r.get("pr_supplier_bin"), r.get("pr_supplier_name"))
            groups.setdefault(key, []).append(r)

        def _action(row: dict) -> str:
            if row.get("ca_override") == "approved":
                return "approved_by_ca"
            if row.get("ca_override") == "ignore":
                return "no_action"
            if row.get("ca_override") == "disputed":
                return "partner_review"
            ms = row["match_status"]
            if ms == "no_match":
                return "chase_supplier"
            if ms == "partial":
                return "partner_review"
            if ms == "fuzzy":
                return "partner_review"
            return "no_action"

        supplier_groups: list[dict[str, Any]] = []
        for (bin_, name), grp in groups.items():
            lines_payload: list[dict[str, Any]] = []
            grp_total = Decimal("0.00")
            for r in grp:
                vat = Decimal(str(r.get("pr_vat_amount_bdt") or "0"))
                grp_total += vat
                lines_payload.append({
                    "line_id": r["id"],
                    "supplier_name": r.get("pr_supplier_name"),
                    "supplier_bin": r.get("pr_supplier_bin"),
                    "invoice_no": r.get("pr_invoice_no"),
                    "invoice_date": r.get("pr_invoice_date"),
                    "taxable_amount_bdt": r.get("pr_taxable_amount_bdt"),
                    "vat_amount_bdt": r.get("pr_vat_amount_bdt"),
                    "match_status": r["match_status"],
                    "match_score": r.get("match_score"),
                    "ca_override": r.get("ca_override"),
                    "ca_notes": r.get("ca_notes"),
                    "recommended_action": _action(r),
                })
            supplier_groups.append({
                "supplier_name": name,
                "supplier_bin": bin_,
                "lines": lines_payload,
                "total_vat_at_risk_bdt": str(grp_total),
                "line_count": len(grp),
            })

        # Sort supplier groups by descending at-risk amount
        supplier_groups.sort(
            key=lambda g: Decimal(g["total_vat_at_risk_bdt"]),
            reverse=True,
        )

        summary = {
            "total_vat_claimed_bdt": recon.get("total_vat_claimed_bdt") or "0",
            "safe_itc_bdt": recon.get("safe_itc_bdt") or "0",
            "at_risk_itc_bdt": recon.get("at_risk_itc_bdt") or "0",
            "total_lines": len(rows),
            "at_risk_line_count": len(at_risk_rows),
            "supplier_count_at_risk": len(supplier_groups),
        }

        return {
            "kind": self.id,
            "recipe_version": self.version,
            "client_id": client["id"],
            "client_name": client["name"],
            "client_bin": client.get("bin"),
            "reconciliation_id": str(reconciliation_id),
            "period_start": recon["period_start"],
            "period_end": recon["period_end"],
            "summary": summary,
            "supplier_groups": supplier_groups,
        }
