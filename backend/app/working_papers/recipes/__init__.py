"""Recipe registry. Add new recipes here as a single import + dict entry."""
from __future__ import annotations

from typing import Any

from app.working_papers.recipes.at_risk_itc import AtRiskItcScheduleRecipe
from app.working_papers.recipes.audit_defense_pack import AuditDefensePackRecipe
from app.working_papers.recipes.base import Recipe


_REGISTRY: dict[str, Recipe] = {
    AtRiskItcScheduleRecipe.id: AtRiskItcScheduleRecipe(),
    AuditDefensePackRecipe.id: AuditDefensePackRecipe(),
}


def get_recipe(recipe_id: str) -> Recipe:
    from app.working_papers.exceptions import RecipeNotFoundError
    if recipe_id not in _REGISTRY:
        raise RecipeNotFoundError(f"Recipe {recipe_id!r} not registered")
    return _REGISTRY[recipe_id]


def all_recipe_ids() -> list[str]:
    return list(_REGISTRY.keys())
