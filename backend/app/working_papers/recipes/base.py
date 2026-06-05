"""Recipe Protocol — the engine's plug-in interface.

A recipe takes typed inputs (e.g. reconciliation_id + tenant_id) and
produces a structured payload. Recipes are pure (no side effects);
persistence and rendering are orthogonal.
"""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class Recipe(Protocol):
    """All recipes implement this. Subclass attribute defaults are fine."""

    id: str           # stable identifier, e.g. "at_risk_itc_schedule"
    version: str      # semver string, e.g. "v1"

    async def compose(self, *, tenant_id: UUID, **inputs: Any) -> dict[str, Any]:
        """Returns a JSON-serializable payload (dict).

        The dict must validate against the recipe's payload schema in
        working_papers.schemas. Service layer trusts this contract.
        """
        ...
