"""Unit tests for Optimizer LEARN copy and render helpers."""

from lib.dash.dash_config import get_theme
from lib.dash.optimizer_glossary import (
    ANALYSIS_ORDER,
    ANALYSIS_SPECS,
    COMBOS_RUN_LABEL,
    CONTROL_HINTS,
    LEARN_SECTIONS,
    QUICK_START_STEPS,
    SECTION_BLURBS,
    WORKFLOW_STEPS,
)
from lib.dash.optimizer_view import (
    render_optimizer_empty_state,
    render_optimizer_learn_content,
)


def test_analysis_specs_cover_order_and_required_keys():
    required = {"name", "aka", "button", "one_liner", "when", "output"}
    assert set(ANALYSIS_ORDER) == set(ANALYSIS_SPECS)
    for key in ANALYSIS_ORDER:
        assert required <= set(ANALYSIS_SPECS[key])
        assert ANALYSIS_SPECS[key]["one_liner"].strip()


def test_learn_sections_and_control_hints_nonempty():
    assert len(QUICK_START_STEPS) >= 4
    assert len(LEARN_SECTIONS) >= 4
    for section in LEARN_SECTIONS:
        assert section["title"] and section["body"]
    for key in (
        "signal_preview",
        "max_signals",
        "max_combos",
        "min_trades",
        "sort_metric",
        "max_dd",
        "min_sharpe",
    ):
        assert CONTROL_HINTS[key].strip()
    for key in ("capital", "universe", "search", "realistic", "bayesian", "param_grid"):
        assert SECTION_BLURBS[key].strip()


def test_combinatorial_aka_mentions_grid_search():
    assert "grid" in ANALYSIS_SPECS["combinatorial"]["aka"].lower()


def test_button_labels_and_workflow_steps():
    assert ANALYSIS_SPECS["combinatorial"]["button"] == COMBOS_RUN_LABEL
    assert "SIGNAL COMBOS" in COMBOS_RUN_LABEL
    assert ANALYSIS_SPECS["bayesian"]["button"] == "TUNE BUNDLE"
    assert ANALYSIS_SPECS["param_grid"]["button"] == "SCAN PARAM GRID"
    assert WORKFLOW_STEPS == ("1 Combos", "2 Tune", "3 Validate")
    assert any("SEARCH SIGNAL COMBOS" in step for step in QUICK_START_STEPS)


def test_render_learn_and_empty_state():
    theme = get_theme()
    learn = render_optimizer_learn_content(theme)
    empty = render_optimizer_empty_state(theme)
    assert learn.className == "sfa-opt-learn-body"
    assert empty.id == "optimizer-empty-state"
    assert empty.className == "sfa-optimize-empty"
