"""High-level service operations called by the FastAPI router."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

from decimal import Decimal

from app.working_papers import persistence as p
from app.working_papers.bundle import (
    EvidenceBundleTooLargeError, build_evidence_zip,
)
from app.working_papers.exceptions import (
    RecipeComposeError,
    WorkingPaperInvalidStateError,
    WorkingPaperNotFoundError,
    WorkingPaperReviewError,
)
from app.working_papers.recipes import get_recipe
from app.working_papers.rendering import (
    PdfRendererUnavailableError,
    render_docx,
    render_pdf,
)
from app.working_papers.schemas import (
    AtRiskItcSchedulePayload,
    AuditDefensePackPayload,
    WorkingPaperEditSource,
    WorkingPaperKind,
    WorkingPaperStatus,
)

log = structlog.get_logger()


_PAYLOAD_VALIDATORS = {
    WorkingPaperKind.AT_RISK_ITC_SCHEDULE: AtRiskItcSchedulePayload,
    WorkingPaperKind.AUDIT_DEFENSE_PACK: AuditDefensePackPayload,
}


async def _fetch_tenant_meta(tenant_id: UUID) -> dict:
    """Letterhead fields from the tenants row. Falls back to neutral defaults."""
    from app.database import get_supabase_admin
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("tenants")
            .select("firm_name, firm_name_bn, icab_reg_no, address, email, phone")
            .eq("id", str(tenant_id))
            .single()
            .execute()
        )

    try:
        res = await asyncio.to_thread(_q)
        row = res.data or {}
    except Exception:
        row = {}
    return {
        "firm_name": row.get("firm_name") or "Chartered Accountants",
        "firm_name_bn": row.get("firm_name_bn") or "",
        "icab_reg_no": row.get("icab_reg_no") or "",
        "address": row.get("address") or "",
        "email": row.get("email") or "",
        "phone": row.get("phone") or "",
    }


async def _fetch_user_names(user_ids: list[Optional[str]]) -> dict[str, str]:
    """Resolve user_profiles.full_name for a set of ids (for the sign-off block)."""
    from app.database import get_supabase_admin
    ids = [u for u in {str(i) for i in user_ids if i}]
    if not ids:
        return {}
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("user_profiles")
            .select("id, full_name")
            .in_("id", ids)
            .execute()
        )

    try:
        res = await asyncio.to_thread(_q)
        return {r["id"]: (r.get("full_name") or "") for r in (res.data or [])}
    except Exception:
        return {}


def _working_paper_reference(wp: dict) -> str:
    """Stable human reference, e.g. WP-1A2B3C4D-202604."""
    wid = str(wp["id"]).replace("-", "")[:8].upper()
    period_end = wp.get("period_end") or ""
    yyyymm = str(period_end).replace("-", "")[:6] if period_end else "000000"
    return f"WP-{wid}-{yyyymm}"


async def compose_working_paper(
    *,
    tenant_id: UUID,
    user_id: UUID,
    kind: WorkingPaperKind,
    reconciliation_id: Optional[UUID] = None,
    notice_id: Optional[UUID] = None,
) -> UUID:
    """Run the recipe, validate, persist. Returns the new working_paper_id."""
    # Recipe IDs match enum values 1:1.
    recipe = get_recipe(kind.value)

    # Per-kind input validation.
    if kind == WorkingPaperKind.AT_RISK_ITC_SCHEDULE:
        if reconciliation_id is None:
            raise WorkingPaperInvalidStateError(
                "reconciliation_id is required for at_risk_itc_schedule",
            )
        inputs: Dict[str, Any] = {"reconciliation_id": reconciliation_id}
    elif kind == WorkingPaperKind.AUDIT_DEFENSE_PACK:
        if notice_id is None:
            raise WorkingPaperInvalidStateError(
                "notice_id is required for audit_defense_pack")
        inputs = {"notice_id": notice_id}
    else:
        inputs = {}

    try:
        payload = await recipe.compose(tenant_id=tenant_id, **inputs)
    except Exception as exc:
        log.exception("working_paper.recipe_compose_failed",
                      kind=kind.value, error=str(exc))
        raise RecipeComposeError(f"Recipe {recipe.id} failed: {exc}") from exc

    # Validate against the strongly-typed schema. Fail fast on contract drift.
    validator = _PAYLOAD_VALIDATORS[kind]
    try:
        validated = validator.model_validate(payload)
    except Exception as exc:
        log.exception("working_paper.payload_invalid",
                      kind=kind.value, error=str(exc))
        raise RecipeComposeError(
            f"Recipe {recipe.id} produced invalid payload: {exc}"
        ) from exc

    # Persist via JSON-mode serialization so Decimals become strings.
    composed_json = validated.model_dump(mode="json")

    wp_id = await p.create_working_paper(
        tenant_id=tenant_id,
        client_id=UUID(str(validated.client_id)),
        kind=kind,
        reconciliation_id=getattr(validated, "reconciliation_id", None),
        notice_id=getattr(validated, "notice_id", None),
        period_start=getattr(validated, "period_start", None),
        period_end=getattr(validated, "period_end", None),
        recipe_version=recipe.version,
        composed_json=composed_json,
        composed_by=user_id,
    )
    log.info(
        "working_paper.composed",
        wp_id=str(wp_id), kind=kind.value, recipe_version=recipe.version,
    )
    return wp_id


async def _fetch_recon_aggregates(
    tenant_id: UUID, recon_id: str,
) -> Optional[dict]:
    """The live headline aggregates for the source reconciliation, used to
    detect whether a composed working paper has gone stale."""
    from app.database import get_supabase_admin
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("vat_reconciliations")
            .select("total_vat_claimed_bdt, safe_itc_bdt, at_risk_itc_bdt")
            .eq("id", str(recon_id))
            .eq("tenant_id", str(tenant_id))
            .single()
            .execute()
        )

    try:
        return (await asyncio.to_thread(_q)).data
    except Exception:
        return None


def _aggregates_differ(snapshot: dict, live: dict) -> bool:
    for key in ("total_vat_claimed_bdt", "safe_itc_bdt", "at_risk_itc_bdt"):
        try:
            if Decimal(str(snapshot.get(key) or "0")) != Decimal(str(live.get(key) or "0")):
                return True
        except Exception:
            return True
    return False


async def get_working_paper(
    *, wp_id: UUID, tenant_id: UUID,
) -> Dict[str, Any]:
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")

    # Staleness: compare the aggregates snapshotted in composed_json against the
    # live reconciliation header. If a CA edited overrides on the recon after
    # this paper was composed, the totals will diverge and the paper is stale.
    # The at-risk schedule holds its summary at the top level; the audit defense
    # pack nests it under reconciled_position.
    wp["is_stale"] = False
    composed = wp.get("composed_json") or {}
    snapshot = composed.get("summary")
    if snapshot is None:
        rp = composed.get("reconciled_position") or {}
        snapshot = rp.get("summary") if isinstance(rp, dict) else None
    recon_id = wp.get("reconciliation_id")
    if recon_id and snapshot:
        live = await _fetch_recon_aggregates(tenant_id, recon_id)
        if live is not None and _aggregates_differ(snapshot, live):
            wp["is_stale"] = True
    return wp


async def update_notes(
    *,
    wp_id: UUID,
    tenant_id: UUID,
    user_id: UUID,
    notes_html: str,
) -> None:
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    if wp["status"] == WorkingPaperStatus.FINALIZED.value:
        raise WorkingPaperInvalidStateError(
            "Working paper is finalized; reopen first",
        )
    await p.update_working_paper(
        wp_id, tenant_id=tenant_id,
        notes_html=notes_html,
        edited_by=user_id,
        edit_source=WorkingPaperEditSource.USER_EDIT,
    )


async def regenerate_working_paper(
    *, wp_id: UUID, tenant_id: UUID, user_id: UUID,
) -> None:
    """Re-run the original recipe with the same inputs and replace composed_json."""
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    if wp["status"] == WorkingPaperStatus.FINALIZED.value:
        raise WorkingPaperInvalidStateError(
            "Working paper is finalized; reopen first",
        )

    kind = WorkingPaperKind(wp["kind"])
    recipe = get_recipe(kind.value)

    inputs: Dict[str, Any] = {}
    if kind == WorkingPaperKind.AT_RISK_ITC_SCHEDULE:
        if wp.get("reconciliation_id") is None:
            raise WorkingPaperInvalidStateError(
                "Cannot regenerate: reconciliation_id missing",
            )
        inputs["reconciliation_id"] = UUID(wp["reconciliation_id"])
    elif kind == WorkingPaperKind.AUDIT_DEFENSE_PACK:
        if wp.get("notice_id") is None:
            raise WorkingPaperInvalidStateError(
                "Cannot regenerate: notice_id missing",
            )
        inputs["notice_id"] = UUID(wp["notice_id"])

    try:
        payload = await recipe.compose(tenant_id=tenant_id, **inputs)
    except Exception as exc:
        log.exception("working_paper.regenerate_failed",
                      wp_id=str(wp_id), error=str(exc))
        raise RecipeComposeError(f"Recipe {recipe.id} failed: {exc}") from exc

    validator = _PAYLOAD_VALIDATORS[kind]
    try:
        validated = validator.model_validate(payload)
    except Exception as exc:
        raise RecipeComposeError(
            f"Recipe {recipe.id} produced invalid payload: {exc}"
        ) from exc

    await p.update_working_paper(
        wp_id, tenant_id=tenant_id,
        composed_json=validated.model_dump(mode="json"),
        edited_by=user_id,
        edit_source=WorkingPaperEditSource.RECIPE_REGENERATED,
    )


async def finalize_working_paper(
    *, wp_id: UUID, tenant_id: UUID, user_id: UUID,
) -> UUID:
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    if wp["status"] == WorkingPaperStatus.FINALIZED.value:
        return UUID(wp["id"])  # idempotent

    # Segregation of duties: the partner who signs off (reviewer) must differ
    # from the staff who prepared the paper (composer).
    if str(wp.get("composed_by")) == str(user_id):
        raise WorkingPaperReviewError(
            "The reviewer who finalizes a working paper must be different from "
            "the preparer who composed it.",
        )

    await p.finalize_working_paper(
        wp_id, tenant_id=tenant_id, finalized_by=user_id,
    )
    return wp_id


async def reopen_working_paper_for_edit(
    *, wp_id: UUID, tenant_id: UUID, user_id: UUID, reason: str,
) -> None:
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    await p.reopen_working_paper(wp_id, tenant_id=tenant_id)
    # Log the reopen as an edit-source row so we have the reason recorded.
    await p.update_working_paper(
        wp_id, tenant_id=tenant_id,
        notes_html=wp.get("notes_html") or "",
        edited_by=user_id,
        edit_source=WorkingPaperEditSource.USER_EDIT,
        edit_reason=f"Reopened: {reason}",
    )


async def export_working_paper(
    *, wp_id: UUID, tenant_id: UUID, format: str,
) -> tuple[bytes, str, str]:
    """Returns (bytes, content_type, filename)."""
    if format not in ("docx", "pdf"):
        raise WorkingPaperInvalidStateError(
            f"Unsupported export format: {format}",
        )
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")

    tenant_meta = await _fetch_tenant_meta(tenant_id)
    names = await _fetch_user_names([wp.get("composed_by"), wp.get("finalized_by")])
    doc_meta = {
        "reference": _working_paper_reference(wp),
        "generated_on": date.today().isoformat(),
        "prepared_by": names.get(str(wp.get("composed_by")), "") or None,
        "reviewed_by": (
            names.get(str(wp.get("finalized_by")), "") or None
            if wp.get("finalized_by") else None
        ),
        "status": wp.get("status"),
    }
    docx_bytes = render_docx(
        payload=wp["composed_json"],
        notes_html=wp.get("notes_html") or "",
        tenant=tenant_meta,
        meta=doc_meta,
    )
    if format == "docx":
        return (
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"working-paper-{wp_id}.docx",
        )
    try:
        pdf_bytes = render_pdf(docx_bytes)
    except PdfRendererUnavailableError as e:
        err = WorkingPaperInvalidStateError(str(e))
        err.default_status = 503
        err.status_code = 503
        raise err
    return (pdf_bytes, "application/pdf", f"working-paper-{wp_id}.pdf")


def _download_evidence(bucket: str, path: str) -> bytes:
    from app.database import get_supabase_admin
    return get_supabase_admin().storage.from_(bucket).download(path)


async def export_evidence_bundle(
    *, wp_id: UUID, tenant_id: UUID,
) -> tuple[bytes, str, str]:
    """Returns (zip_bytes, content_type, filename) for an audit_defense_pack."""
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
    if wp["kind"] != WorkingPaperKind.AUDIT_DEFENSE_PACK.value:
        raise WorkingPaperInvalidStateError(
            "Evidence bundle is only available for an audit defense pack")

    # Reuse the docx export (also resolves letterhead + sign-off meta).
    docx_bytes, _ctype, _fname = await export_working_paper(
        wp_id=wp_id, tenant_id=tenant_id, format="docx")

    payload = wp["composed_json"] or {}
    evidence = payload.get("evidence_index") or []
    reference = _working_paper_reference(wp)

    def _build() -> bytes:
        return build_evidence_zip(
            binder_docx=docx_bytes, evidence=evidence,
            download=_download_evidence, reference=reference)

    try:
        zip_bytes = await asyncio.to_thread(_build)
    except EvidenceBundleTooLargeError as e:
        err = WorkingPaperInvalidStateError(str(e))
        err.default_status = 413
        err.status_code = 413
        raise err
    return (zip_bytes, "application/zip", f"audit-defense-pack-{reference}.zip")


async def list_working_papers(
    *,
    tenant_id: UUID,
    client_id: Optional[UUID] = None,
    kind: Optional[WorkingPaperKind] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    return await p.list_working_papers(
        tenant_id=tenant_id, client_id=client_id, kind=kind, limit=limit,
    )
