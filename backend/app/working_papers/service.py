"""High-level service operations called by the FastAPI router."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog

from app.working_papers import persistence as p
from app.working_papers.exceptions import (
    RecipeComposeError,
    WorkingPaperInvalidStateError,
    WorkingPaperNotFoundError,
)
from app.working_papers.recipes import get_recipe
from app.working_papers.rendering import (
    PdfRendererUnavailableError,
    render_docx,
    render_pdf,
)
from app.working_papers.schemas import (
    AtRiskItcSchedulePayload,
    WorkingPaperEditSource,
    WorkingPaperKind,
    WorkingPaperStatus,
)

log = structlog.get_logger()


_PAYLOAD_VALIDATORS = {
    WorkingPaperKind.AT_RISK_ITC_SCHEDULE: AtRiskItcSchedulePayload,
}


async def _fetch_tenant_meta(tenant_id: UUID) -> dict:
    """Letterhead fields from the tenants row. Falls back to neutral defaults."""
    from app.database import get_supabase_admin
    sb = get_supabase_admin()

    def _q():
        return (
            sb.table("tenants")
            .select("*")
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
        "firm_name": row.get("name") or row.get("firm_name") or "Chartered Accountants",
        "address": row.get("address") or "",
    }


async def compose_working_paper(
    *,
    tenant_id: UUID,
    user_id: UUID,
    kind: WorkingPaperKind,
    reconciliation_id: Optional[UUID] = None,
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


async def get_working_paper(
    *, wp_id: UUID, tenant_id: UUID,
) -> Dict[str, Any]:
    wp = await p.get_working_paper(wp_id, tenant_id=tenant_id)
    if wp is None:
        raise WorkingPaperNotFoundError(f"Working paper {wp_id} not found")
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
    docx_bytes = render_docx(
        payload=wp["composed_json"],
        notes_html=wp.get("notes_html") or "",
        tenant=tenant_meta,
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
