"""Notice linker — decides what reconciliation (if any) a notice attaches to.

Pure orchestration over two DB helpers in app/notices/persistence.py.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from app.notices.persistence import (
    find_client_ids_by_bin, find_recon_by_period,
)
from app.notices.schemas import (
    LinkedRecon, LinkerResult, NeedsIngestion, NeedsManualLink, ParsedNotice,
)


async def link_notice(parsed: ParsedNotice, *, tenant_id: UUID) -> LinkerResult:
    if not parsed.taxpayer_bin:
        return NeedsManualLink(candidate_clients=[])

    client_ids: List[UUID] = await find_client_ids_by_bin(
        parsed.taxpayer_bin, tenant_id=tenant_id,
    )
    if not client_ids:
        return NeedsManualLink(candidate_clients=[])
    if len(client_ids) > 1:
        return NeedsManualLink(candidate_clients=client_ids)

    only_client = client_ids[0]
    if not parsed.period_start or not parsed.period_end:
        return NeedsManualLink(candidate_clients=[only_client])

    recon_id: Optional[UUID] = await find_recon_by_period(
        client_id=only_client, tenant_id=tenant_id,
        period_start=parsed.period_start, period_end=parsed.period_end,
    )
    if recon_id:
        return LinkedRecon(reconciliation_id=recon_id, client_id=only_client)
    return NeedsIngestion(
        client_id=only_client,
        period_start=parsed.period_start,
        period_end=parsed.period_end,
    )
