"""Guards on the vendored Lightweight Charts bundle and its glue.

The chart is drawn by browser JavaScript that no Python test exercises, so a bad
upgrade or a rename would show up only as a blank canvas at runtime. These
checks are cheap and fail loudly at the exact place the breakage was introduced.
"""

import re
from pathlib import Path

import pytest

ASSETS = Path(__file__).resolve().parents[1] / "dash" / "assets"
VENDOR = ASSETS / "00-lightweight-charts.standalone.production.js"
GLUE = ASSETS / "10-sfa-chart.js"

# Bump together with the vendored file and the table in assets/VENDOR.md.
EXPECTED_VERSION = "5.2.0"

# Every Lightweight Charts export the glue calls. A v5→v6 rename would drop the
# chart without any Python-side error.
REQUIRED_EXPORTS = [
    "createChart",
    "CandlestickSeries",
    "BarSeries",
    "LineSeries",
    "AreaSeries",
    "BaselineSeries",
    "HistogramSeries",
    "createSeriesMarkers",
]


@pytest.fixture(scope="module")
def vendor_src() -> str:
    return VENDOR.read_text(encoding="utf-8", errors="ignore")


@pytest.fixture(scope="module")
def glue_src() -> str:
    return GLUE.read_text(encoding="utf-8")


def test_vendor_bundle_is_present():
    assert VENDOR.is_file(), f"missing vendored bundle: {VENDOR}"
    assert VENDOR.stat().st_size > 100_000


def test_vendor_bundle_is_the_pinned_version(vendor_src):
    assert f'version:function(){{return"{EXPECTED_VERSION}"}}' in vendor_src.replace(" ", "")


def test_vendor_bundle_keeps_its_licence_header(vendor_src):
    """Apache-2.0 attribution — see assets/VENDOR.md."""
    head = vendor_src[:400]
    assert "Lightweight Charts" in head
    assert "Apache License 2.0" in head


def test_vendor_bundle_exposes_the_global(vendor_src):
    assert "window.LightweightCharts" in vendor_src


@pytest.mark.parametrize("symbol", REQUIRED_EXPORTS)
def test_vendor_bundle_exports_what_the_glue_uses(vendor_src, symbol):
    assert symbol in vendor_src


def test_glue_is_present_and_registers_the_namespace(glue_src):
    assert "window.sfaChart" in glue_src


def test_glue_loads_after_the_vendor_bundle():
    """Dash injects assets in sorted filename order; the numeric prefixes pin it."""
    assert VENDOR.name < GLUE.name
    assert re.match(r"^\d\d-", VENDOR.name)
    assert re.match(r"^\d\d-", GLUE.name)


def test_glue_guards_on_the_library_being_loaded(glue_src):
    """Belt-and-braces for the ordering above."""
    assert "window.LightweightCharts" in glue_src


def test_attribution_logo_is_not_disabled(glue_src):
    """Apache-2.0 requires attribution; the built-in logo satisfies it."""
    assert "attributionLogo: true" in glue_src
    assert "attributionLogo: false" not in glue_src


@pytest.mark.parametrize("method", [
    "apply", "setChartType", "setScaleMode", "setTheme",
    "fitContent", "setVisibleRange", "screenshot", "isReady",
])
def test_glue_exposes_the_api_the_callbacks_call(glue_src, method):
    """These names are referenced from clientside callbacks, which fail silently."""
    assert re.search(rf"\b{method}\s*:", glue_src), f"window.sfaChart.{method} is missing"


def test_glue_lowers_min_bar_spacing_so_fit_can_show_every_bar(glue_src):
    """`fitContent` is clamped by `minBarSpacing`, and the default hides data.

    Lightweight Charts defaults `minBarSpacing` to 0.5px, so a series wider than
    `pane_width / 0.5` bars cannot be fully zoomed out. Measured on a 1,092px
    pane: a 3,473-bar 1H series fit only 2,027 bars — FIT showed 58% of the
    loaded range with no indication the rest existed. Anything above ~0.05
    reintroduces that ceiling at intraday widths.
    """
    match = re.search(r"minBarSpacing:\s*([0-9.]+)", glue_src)
    assert match, "minBarSpacing is unset — fitContent will silently clip"
    assert float(match.group(1)) <= 0.05


def test_glue_only_sets_bar_spacing_on_first_creation(glue_src):
    """Re-applying `barSpacing` on every payload silently resets the zoom.

    `ensureChart` calls `applyOptions(chartOptions(...))` on every update, so a
    viewport option living in that object is re-imposed whenever the user
    toggles an indicator, cycles the theme, or changes chart type. Measured
    before the fix: a 1,962-bar window snapped back to 126. `barSpacing` and
    `rightOffset` describe where the chart *starts*, so they belong behind the
    `initial` flag that only `createChart` passes.
    """
    guarded = re.search(
        r"if \(initial\) \{(.*?)\}", glue_src, re.S
    )
    assert guarded, "the `initial` guard in chartOptions is gone"
    for option in ("barSpacing", "rightOffset"):
        assert option in guarded.group(1), f"{option} escaped the initial guard"
        assert glue_src.count(option + ":") == 0, (
            f"{option} is still set unconditionally in chartOptions"
        )


def test_vendor_notice_file_exists():
    assert (ASSETS / "VENDOR.md").is_file()
