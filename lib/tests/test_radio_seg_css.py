"""Regression: Dash 4 RadioItems segment CSS must keep radios clickable."""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "dash" / "assets"
CONTROLS = ASSETS / "20-controls.css"
VENDOR_WIDGETS = ASSETS / "30-vendor-widgets.css"


def _segment_block() -> str:
    text = CONTROLS.read_text(encoding="utf-8")
    start = text.index("Segmented RadioItems")
    end = text.index("Section primitives", start)
    return text[start:end]


def test_bbg_radio_seg_does_not_display_none_inputs():
    """display:none on Dash 4 radios blocks label/onChange activation."""
    seg = _segment_block()
    assert "display: none" not in seg
    assert "opacity: 0 !important" in seg


def test_bbg_radio_seg_styles_dash4_selected_state():
    seg = _segment_block()
    assert "label.selected" in seg
    assert 'aria-selected="true"' in seg


def test_dropdown_options_list_styles_exclude_segment_radios():
    text = VENDOR_WIDGETS.read_text(encoding="utf-8")
    assert "dash-options-list:not(.bbg-radio-seg)" in text
