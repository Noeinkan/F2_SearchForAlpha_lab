"""
Shared helpers for dashboard callback modules.

Implementation lives in focused sibling modules; this file re-exports the
public surface so existing ``from lib.dash.callbacks.shared import ...``
call sites keep working.
"""

from __future__ import annotations

from lib.dash.dash_config import DATA_EXPORT_MAX_ROWS  # noqa: F401  — tests patch this name

from .shared_enrichment import (  # noqa: F401
    _ENRICHED_CACHE,
    _ENRICHED_CACHE_MAX,
    _build_indicator_settings_panel,
    _rebuild_indicator_dataframe,
    clear_enriched_cache,
    get_enriched,
    parse_date_bound,
    slice_df_to_window,
)
from .shared_signals import (  # noqa: F401
    SIGNAL_DESCRIPTIONS,
    _build_plot_toggle_values,
    _build_signal_options,
    _build_unified_signal_rows,
    _collect_selected_plots,
    _compute_trigger_counts,
    _describe_signal,
    _extract_selected_plots,
    _format_signal_label,
    _strip_signal_side,
)
from .shared_data_display import (  # noqa: F401
    _create_data_table,
    _create_summary_strip,
    build_data_display_payload,
    build_data_table_style_rules,
    classify_data_column_groups,
    compute_data_summary,
    filter_data_display,
    records_to_csv,
)
from .shared_presets import (  # noqa: F401
    _build_preset_payload,
    _format_preset_options,
    _preset_status,
    _sanitize_preset_name,
)
from .shared_optimization_ui import (  # noqa: F401
    OPTIMIZATION_BATCH_SIZE,
    _create_best_strategy_highlight,
    _create_optimization_table,
    _create_optimization_table_mini,
    _create_price_subtitle,
)

# records_to_csv reads DATA_EXPORT_MAX_ROWS from shared_data_display at call
# time via this module when tests patch ``shared.DATA_EXPORT_MAX_ROWS``.
import lib.dash.callbacks.shared_data_display as _data_display

_orig_records_to_csv = records_to_csv


def records_to_csv(records, columns):  # type: ignore[no-redef]
    """Wrap so tests can patch ``shared.DATA_EXPORT_MAX_ROWS``."""
    previous = _data_display.DATA_EXPORT_MAX_ROWS
    _data_display.DATA_EXPORT_MAX_ROWS = DATA_EXPORT_MAX_ROWS
    try:
        return _orig_records_to_csv(records, columns)
    finally:
        _data_display.DATA_EXPORT_MAX_ROWS = previous
