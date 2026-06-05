from app.working_papers.exceptions import (
    RecipeComposeError,
    RecipeNotFoundError,
    WorkingPaperError,
    WorkingPaperInvalidStateError,
    WorkingPaperNotFoundError,
)


def test_working_paper_not_found_404():
    e = WorkingPaperNotFoundError("missing")
    assert e.code == "WORKING_PAPER_NOT_FOUND"
    assert e.status_code == 404


def test_recipe_not_found_400():
    e = RecipeNotFoundError("no such recipe")
    assert e.code == "RECIPE_NOT_FOUND"
    assert e.status_code == 400


def test_working_paper_invalid_state_409():
    e = WorkingPaperInvalidStateError("already finalized")
    assert e.code == "WORKING_PAPER_INVALID_STATE"
    assert e.status_code == 409


def test_recipe_compose_error_400():
    e = RecipeComposeError("compose failed")
    assert e.code == "RECIPE_COMPOSE_ERROR"
    assert e.status_code == 400


def test_all_inherit_from_working_paper_error():
    for cls in (
        WorkingPaperNotFoundError,
        RecipeNotFoundError,
        WorkingPaperInvalidStateError,
        RecipeComposeError,
    ):
        assert issubclass(cls, WorkingPaperError)
