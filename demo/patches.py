"""Swaps the dashboard's live seams for the frozen snapshot.

Each patch replaces one function at the point where the dashboard reaches the
outside world or the disk, and leaves everything downstream of it unchanged,
so the demo exercises the same indicator, backtest and optimiser code as the
workspace does.

``rebind`` is the mechanism. Replacing a module attribute is not enough on
its own, because ``from lib.x import f`` copies the reference into the
importing module at import time; ``rebind`` also walks every loaded ``lib.``
and ``scripts.`` module and swaps any name still pointing at the original.
It therefore has to run after the dashboard modules are imported, which
``demo.server.create_demo_app`` guarantees.
"""

from __future__ import annotations

import contextvars
import importlib
import logging
import sys
import threading
import types
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from demo import snapshot
from demo.settings import DemoSettings

logger = logging.getLogger(__name__)

FLOW_OFF_MESSAGE = (
    "The Flow Scanner reads a live options chain, so it is switched off in this public demo. "
    "Everything else here runs on a frozen snapshot."
)


def rebind(module_name: str, attr: str, replacement: Any) -> Any:
    """Replace ``module.attr`` everywhere it has been imported. Returns the original."""
    module = importlib.import_module(module_name)
    original = getattr(module, attr)
    setattr(module, attr, replacement)
    for name, loaded in list(sys.modules.items()):
        if not isinstance(loaded, types.ModuleType) or not name.startswith(("lib.", "scripts.")):
            continue
        namespace = vars(loaded)
        for key, value in list(namespace.items()):
            if value is original:
                setattr(loaded, key, replacement)
    return original


# --------------------------------------------------------------------------- context carriers


class ContextExecutor:
    """A shared thread pool whose tasks run inside the submitter's context.

    Replaces the optimiser's module-level pool. Two things change for the
    demo: the pool is capped at ``optimizer_workers`` for everyone, and
    ``shutdown`` becomes a no-op -- the original shuts the pool down whenever
    any run starts or stops, which on a shared server would cancel every other
    visitor's in-flight batch.
    """

    def __init__(self, workers: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="demo-opt")

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        ctx = contextvars.copy_context()
        return self._pool.submit(ctx.run, fn, *args, **kwargs)

    def shutdown(self, wait: bool = False, cancel_futures: bool = False) -> None:  # noqa: ARG002
        return None


class ContextThread(threading.Thread):
    """``threading.Thread`` that runs its target inside the starter's context."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._demo_context = contextvars.copy_context()

    def run(self) -> None:
        self._demo_context.run(super().run)


class _ThreadingShim(types.ModuleType):
    """What ``threading`` looks like to the optimiser workspace modules."""

    Thread = ContextThread

    def __getattr__(self, name: str) -> Any:
        return getattr(threading, name)


# --------------------------------------------------------------------------- data seams


def _patch_prices() -> None:
    import lib.data_processing as dp

    # fetch_data calls _yahoo_history through the module global, so a plain
    # attribute swap reaches every caller: dashboard loads, grid search,
    # Bayesian sweeps and walk-forward validation alike.
    dp._yahoo_history = snapshot.load_bars

    def validate_symbol(symbol: str, cache_hit: bool = True) -> bool:  # noqa: ARG001
        return snapshot.has_ticker(symbol)

    rebind("lib.data_processing", "validate_symbol", validate_symbol)

    import lib.timeframes as tf

    original_full = tf.full_history_window
    original_clamp = tf.clamp_window

    def full_history_window(interval, *, as_of=None):
        return original_full(interval, as_of=as_of or snapshot.snapshot_now())

    def clamp_window(start, end, interval, *, as_of=None, relocate=False):
        return original_clamp(start, end, interval, as_of=as_of or snapshot.snapshot_now(), relocate=relocate)

    rebind("lib.timeframes", "full_history_window", full_history_window)
    rebind("lib.timeframes", "clamp_window", clamp_window)

    # The parquet cache under state/ would outlive a visitor; the snapshot is
    # already on disk and reads in milliseconds, so the demo skips the cache.
    import lib.dash.ohlcv_disk_cache as cache

    cache.load_frame = lambda ticker, interval: None
    cache.write_frame = lambda ticker, interval, df: None
    cache.schedule_revalidate = lambda *args, **kwargs: False


def _patch_fundamentals() -> None:
    rebind("lib.fundamentals", "fetch_fundamentals", lambda ticker, years=None: snapshot.load_fundamentals(ticker))


def _patch_symbols() -> None:
    import lib.dash.symbol_quotes as quotes
    import lib.dash.ticker_search as search
    import lib.ticker_universe as universe

    original_from_disk = universe._load_from_disk

    def load_demo_universe():
        frame = original_from_disk()
        if frame is None:
            return None
        return frame[frame["Symbol"].isin(snapshot.tickers())].reset_index(drop=True)

    universe._load_from_disk = load_demo_universe
    # The fallback fetches ticker lists from Wikipedia and GitHub.
    universe._load_fallback = load_demo_universe
    universe.clear_cache()
    search.clear_index_cache()

    def fixture_quotes(symbols):
        out = {}
        for symbol in symbols:
            closes = snapshot.last_closes(symbol)
            if closes:
                last, prev = closes
                out[symbol] = quotes.SymbolQuote(
                    symbol=symbol, price=last, change_pct=((last - prev) / prev) * 100.0 if prev else None
                )
        return out

    quotes._fetch_yfinance_quotes = fixture_quotes
    quotes.clear_quote_cache()


def _patch_writes() -> None:
    """Presets and watchlists stay in the visitor's browser; nothing reaches config/.

    The last-session file is switched off in both directions: it is one file
    for the whole process, so one visitor's workspace would become every next
    visitor's starting point.
    """
    from lib.dash.watchlist_storage import normalize

    rebind("lib.dash.preset_storage", "save_presets", lambda path, data: None)
    rebind("lib.dash.watchlist_storage", "save_watchlists", lambda path, data: normalize(data))
    rebind("lib.dash.ui_session_storage", "load_ui_session", lambda path: None)
    rebind("lib.dash.ui_session_storage", "save_ui_session", lambda path, payload: False)


def _patch_flow() -> None:
    from pathlib import Path

    import lib.dash.flow_store as flow_store
    import lib.dash.integrated_dashboard as dashboard

    def refuse_scan(*args: Any, **kwargs: Any) -> tuple[int, str]:  # noqa: ARG001
        return 1, FLOW_OFF_MESSAGE

    # run_flow_scan starts scripts/flow_scanner.py as a subprocess, which the
    # in-process network seal would not cover.
    rebind("scripts.flow_runner", "run_flow_scan", refuse_scan)
    # No stored per-ticker reports either, whatever the host's state/ holds.
    flow_store.FLOW_DIR = Path("/nonexistent/flow")
    dashboard.DEFAULT_FLOW_REPORT = "/nonexistent/flow_report.html"
    dashboard._FLOW_STUB_HTML = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Flow Scanner</title>"
        "<style>body{background:#0d1117;color:#c9d1d9;font-family:system-ui;padding:24px;}</style>"
        f"</head><body><h1>Not in the demo</h1><p>{FLOW_OFF_MESSAGE}</p></body></html>"
    )


def _patch_optimiser(settings: DemoSettings) -> None:
    import lib.dash.callbacks.optimization as optimization

    executor = ContextExecutor(settings.optimizer_workers)
    optimization._get_executor = lambda: executor
    optimization._shutdown_executor = lambda: None
    # Shown in the progress line ("2 workers") and used for the ETA.
    optimization.OPTIMIZER_WORKERS = settings.optimizer_workers

    shim = _ThreadingShim("threading")
    for name in ("lib.dash.callbacks.optimizer_grid", "lib.dash.callbacks.optimizer_phase3"):
        module = importlib.import_module(name)
        module.threading = shim


_ORIGINAL_DATA_DISPLAY: dict[str, Callable] = {}


def _patch_data_display() -> None:
    """Build the Data table payload only for visitors who open the Data view.

    The workspace builds it on every load and embeds it in the page: ~10 MB of
    JSON for twenty years of bars and indicators, which the browser then POSTs
    straight back to the server because the table callback takes the store as
    an input. Locally that is free. On a public page it is a 10 MB upload per
    visit, so the demo sends ``None`` until the Data view is opened
    (``register_lazy_data_display``).
    """
    original = rebind("lib.dash.callbacks.shared_data_display", "build_data_display_payload", lambda df: None)
    _ORIGINAL_DATA_DISPLAY["build"] = original


def register_lazy_data_display(app) -> None:
    from dash import Input, Output, State
    from dash.exceptions import PreventUpdate

    from lib.dash.callbacks.shared import get_enriched
    from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, merge_indicator_settings

    build = _ORIGINAL_DATA_DISPLAY["build"]

    @app.callback(
        Output("data-display-store", "data", allow_duplicate=True),
        Input("open-data-button", "n_clicks"),
        Input("open-data-from-optimizer", "n_clicks"),
        State("indicator-settings-store", "data"),
        prevent_initial_call=True,
    )
    def demo_fill_data_table(_open_backtest, _open_optimizer, indicator_settings):
        from lib.dash.state import dashboard_state

        if dashboard_state.df is None:
            raise PreventUpdate
        settings = merge_indicator_settings(indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        return build(get_enriched(dashboard_state.df, settings))


def install(settings: DemoSettings) -> None:
    """Install every seam. Call after importing lib.dash.integrated_dashboard."""
    if "lib.dash.integrated_dashboard" not in sys.modules:
        raise RuntimeError("demo.patches.install() must run after the dashboard modules are imported")
    _patch_prices()
    _patch_fundamentals()
    _patch_symbols()
    _patch_writes()
    _patch_flow()
    _patch_optimiser(settings)
    _patch_data_display()
    logger.info("demo seams installed: snapshot %s, %d tickers", snapshot.snapshot_date(), len(snapshot.tickers()))


def install_session_state(store) -> None:
    """Replace the dashboard_state singleton with the per-visitor proxy."""
    from demo.sessions import SessionScopedState

    rebind("lib.dash.state", "dashboard_state", SessionScopedState(store))
