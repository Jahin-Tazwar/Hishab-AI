"""Verifies the Windows-only event-loop policy pin in app.main."""
from __future__ import annotations

import asyncio
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Selector policy pin only matters on Windows",
)


def test_main_module_pins_selector_event_loop_policy() -> None:
    # Importing app.main has the side effect of setting the policy at
    # module load. We re-import via importlib to make the assertion
    # robust if the test runner imports main earlier.
    import importlib
    import app.main as main_module
    importlib.reload(main_module)

    policy = asyncio.get_event_loop_policy()
    assert isinstance(policy, asyncio.WindowsSelectorEventLoopPolicy), (
        f"Expected WindowsSelectorEventLoopPolicy, got {type(policy).__name__}"
    )
