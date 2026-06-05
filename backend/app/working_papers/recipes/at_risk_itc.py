"""At-Risk ITC Schedule recipe — composes the client-facing deliverable
from a reconciliation_id.

Pulls the recon header + lines via persistence helpers. Filters to the
lines that are genuinely at-risk using the SAME arbiter the headline KPI
uses (`reconciliation.buckets.effective_bucket`), so the sum of per-supplier
at-risk VAT always ties to `vat_reconciliations.at_risk_itc_bdt`. Groups by
supplier, carries the supplier-side figures + variance for each line, and
tags each line with a recommended action.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database import get_supabase_admin
from app.reconciliation.buckets import effective_bucket


# PostgREST caps an unpaginated response at 1000 rows; we page explicitly so
# a large purchase register never silently truncates the schedule.
_PAGE = 1000


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

        def _q_lines(offset: int, limit: int):
            return (
                sb.table("recon_line_items")
                .select(
                    "id, pr_invoice_no, pr_supplier_bin, pr_supplier_name, "
                    "pr_invoice_date, pr_taxable_amount_bdt, pr_vat_amount_bdt, "
                    "sf_invoice_no, sf_invoice_date, sf_taxable_amount_bdt, "
                    "sf_vat_amount_bdt, match_status, match_score, "
                    "discrepancy_flags, ca_override, ca_notes"
                )
                .eq("tenant_id", str(tenant_id))
                .eq("reconciliation_id", str(reconciliation_id))
                .order("pr_supplier_name")
                .order("pr_invoice_date")
                .range(offset, offset + limit - 1)
                .execute()
            )

        recon = (await asyncio.to_thread(_q_recon)).data
        client = (await asyncio.to_thread(_q_client, recon["client_id"])).data

        # Page through ALL line items — never rely on the default row cap.
        rows: list[dict] = []
        while True:
            batch = (await asyncio.to_thread(_q_lines, len(rows), _PAGE)).data or []
            rows.extend(batch)
            if len(batch) < _PAGE:
                break

        # Filter to at-risk lines using the single source of truth shared with
        # the recon engine's headline KPI. effective_bucket maps:
        #   exact/fuzzy -> safe, approved -> safe, ignore -> excluded,
        #   partial/no_match -> at_risk, disputed -> at_risk.
        # Result: Σ per-supplier at-risk VAT == recon.at_risk_itc_bdt exactly.
        at_risk_rows = [
            r for r in rows
            if effective_bucket(r["match_status"], r.get("ca_override")) == "at_risk"
        ]

        # Group by (supplier_bin, supplier_name)
        groups: dict[tuple[str | None, str | None], list[dict]] = {}
        for r in at_risk_rows:
            key = (r.get("pr_supplier_bin"), r.get("pr_supplier_name"))
            groups.setdefault(key, []).append(r)

        supplier_groups: list[dict[str, Any]] = []
        for (bin_, name), grp in groups.items():
            lines_payload: list[dict[str, Any]] = []
            grp_total = Decimal("0.00")
            for r in grp:
                # Every row here is at_risk by construction, so its full claimed
                # VAT contributes to the at-risk total (ties to the headline).
                vat = Decimal(str(r.get("pr_vat_amount_bdt") or "0"))
                grp_total += vat
                sf_vat = r.get("sf_vat_amount_bdt")
                flags = r.get("discrepancy_flags") or {}
                lines_payload.append({
                    "line_id": r["id"],
                    "supplier_name": r.get("pr_supplier_name"),
                    "supplier_bin": r.get("pr_supplier_bin"),
                    "invoice_no": r.get("pr_invoice_no"),
                    "invoice_date": r.get("pr_invoice_date"),
                    "taxable_amount_bdt": r.get("pr_taxable_amount_bdt"),
                    "vat_amount_bdt": r.get("pr_vat_amount_bdt"),
                    # Supplier-reported figures + the gap — this comparison IS
                    # the at-risk analysis. None sf_vat (no_match) => full claim
                    # is the exposure.
                    "sf_taxable_amount_bdt": r.get("sf_taxable_amount_bdt") or None,
                    "sf_vat_amount_bdt": sf_vat or None,
                    "vat_variance_bdt": str(vat - Decimal(str(sf_vat or "0"))),
                    "discrepancy_reason": flags.get("reason"),
                    "date_off_by_days": flags.get("date_off_by_days"),
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


def _action(row: dict) -> str:
    """Map a line to a recommended CA action.

    NOTE: taxonomy pending a short validation with a practicing CA before the
    client-facing labels are locked. Current mapping keeps every enum value
    reachable and ties the advice to the evidence:
      approved -> approved_by_ca   (defensive; approved lines are safe and are
                                    filtered out before this is reached)
      ignore   -> no_action        (defensive; ignored lines are excluded)
      disputed -> reverse_claim    (CA reviewed and rejected -> reverse the ITC)
      no_match -> chase_supplier   (supplier never filed -> ask them to file)
      partial  -> partner_review   (amounts differ materially -> judgment call)
      fuzzy    -> partner_review   (defensive; fuzzy is safe and filtered out)
    """
    ov = row.get("ca_override")
    if ov == "approved":
        return "approved_by_ca"
    if ov == "ignore":
        return "no_action"
    if ov == "disputed":
        return "reverse_claim"
    ms = row["match_status"]
    if ms == "no_match":
        return "chase_supplier"
    if ms == "partial":
        return "partner_review"
    return "partner_review"
