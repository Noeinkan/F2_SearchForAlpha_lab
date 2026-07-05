"""
Phase 9 — layout snapshot + style-invariant tests.

Guards the top-level component tree (IDs and region classes) and the
``min-width: 0`` / ``flex: 1 1 0`` invariants that keep the chart from
collapsing (the Phase 1 fix). These are structural regression tripwires: if a
refactor drops a store, renames a region, or reintroduces the collapse bug,
one of these fails.
"""

import pytest

from lib.dash.layout.shell import create_dashboard_layout
from lib.dash.styles import get_styles
from lib.dash.dash_config import get_theme


def _walk(component):
    """Yield every component in the tree (depth-first)."""
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children") or hasattr(child, "id"):
            yield from _walk(child)


def _collect(component, attr):
    values = set()
    for comp in _walk(component):
        val = getattr(comp, attr, None)
        if isinstance(val, str):
            values.add(val)
    return values


@pytest.fixture(scope="module")
def layout():
    return create_dashboard_layout(get_theme())


@pytest.fixture(scope="module")
def ids(layout):
    return _collect(layout, "id")


@pytest.fixture(scope="module")
def class_names(layout):
    # className strings can be multi-token ("dot dot-up") — split them.
    names = set()
    for value in _collect(layout, "className"):
        names.update(value.split())
    return names


# --- Top-level structural IDs -------------------------------------------------

EXPECTED_SHELL_IDS = {
    "app-container",
    "terminal-shell",
    "financial-chart",
    "chart-frame",
    "ticker-dropdown",
    "data-status",
    "strategy-order-status",
    "run-backtest-btn",
    "backtest-results",
    "run-optimization-btn",
    "optimization-results",
    "command-palette",
}


@pytest.mark.parametrize("component_id", sorted(EXPECTED_SHELL_IDS))
def test_shell_id_present(ids, component_id):
    assert component_id in ids, f"missing top-level component id: {component_id}"


def test_phase7_status_activity_ids_present(ids):
    """Phase 7 wired the status-bar activity segment to lifecycle callbacks."""
    assert "status-activity-label" in ids
    assert "status-activity-dot" in ids


def test_phase8_perf_ids_present(ids):
    """Phase 8 added the bar-count readout and the zoom-range store."""
    assert "chart-bar-count" in ids
    assert "chart-view-range-store" in ids


def test_region_classes_present(class_names):
    for region in ("sfa-sidebar", "sfa-right-panel", "bbg-status-bar", "sfa-splitter"):
        assert region in class_names, f"missing region class: {region}"


# --- Style invariants (the Phase 1 chart-collapse fix) ------------------------

def test_chart_container_has_min_width_zero():
    styles = get_styles(get_theme())
    assert styles["chart_container"].get("minWidth") == 0
    assert styles["chart_container"].get("flex") == "1 1 0"


def test_main_container_has_min_width_zero():
    styles = get_styles(get_theme())
    assert styles["main_container"].get("minWidth") == 0
