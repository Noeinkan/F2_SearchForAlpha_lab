"""
Dashboard Styles
Style generators for dashboard components.
"""

from lib.dash.dash_config import (
    FONT_FAMILY, FONT_MONO, FONT_SIZES, BORDER_RADIUS
)


def get_styles(theme: dict) -> dict:
    """
    Generate component styles based on theme.

    Args:
        theme: Theme configuration dict

    Returns:
        Dict of style definitions for various components
    """
    return {
        'app': {
            'fontFamily': FONT_FAMILY,
            'backgroundColor': theme['bg_primary'],
            'color': theme['text_primary'],
            'minHeight': '100vh',
            'margin': 0,
            'padding': 0,
        },
        'header': {
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'padding': '12px 20px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'height': '56px',
        },
        'logo': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '12px',
        },
        'logo_icon': {
            'width': '32px',
            'height': '32px',
            'backgroundColor': theme['accent_blue'],
            'borderRadius': BORDER_RADIUS['md'],
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'color': '#fff',
            'fontWeight': 'bold',
            'fontSize': FONT_SIZES['lg'],
        },
        'logo_text': {
            'fontSize': FONT_SIZES['lg'],
            'fontWeight': '600',
            'color': theme['text_primary'],
            'letterSpacing': '-0.5px',
        },
        'header_controls': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '16px',
        },
        'main_container': {
            'display': 'flex',
            'height': 'calc(100vh - 56px)',
            'overflow': 'hidden',
        },
        'sidebar': {
            'width': '280px',
            'minWidth': '280px',
            'backgroundColor': theme['bg_secondary'],
            'borderRight': f'1px solid {theme["border_primary"]}',
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden',
        },
        'sidebar_section': {
            'padding': '16px',
            'borderBottom': f'1px solid {theme["border_secondary"]}',
        },
        'indicator_label_row': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '8px',
            'width': '100%',
        },
        'indicator_row': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '8px',
            'width': '100%',
        },
        'indicator_gear_button': {
            'marginLeft': 'auto',
            'backgroundColor': 'transparent',
            'border': f'1px solid {theme["border_secondary"]}',
            'borderRadius': BORDER_RADIUS['sm'],
            'color': theme['text_secondary'],
            'fontSize': '12px',
            'width': '22px',
            'height': '22px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'cursor': 'pointer',
            'padding': 0,
            'pointerEvents': 'auto',
            'zIndex': 1,
        },
        'indicator_gear_button_active': {
            'border': f'1px solid {theme["border_focus"]}',
            'color': theme['text_primary'],
        },
        'indicator_settings_panel': {
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '8px',
        },
        'indicator_setting_row': {
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'gap': '12px',
        },
        'indicator_setting_label': {
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
        },
        'indicator_setting_input': {
            'backgroundColor': theme['bg_tertiary'],
            'border': f'1px solid {theme["border_primary"]}',
            'borderRadius': BORDER_RADIUS['sm'],
            'color': theme['text_primary'],
            'padding': '6px 8px',
            'fontSize': FONT_SIZES['xs'],
            'width': '120px',
        },
        'indicator_settings_empty': {
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_tertiary'],
            'padding': '6px 0',
        },
        'sidebar_title': {
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': '600',
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'marginBottom': '6px',
        },
        'chart_container': {
            'flex': 1,
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden',
            'backgroundColor': theme['bg_primary'],
        },
        'chart_toolbar': {
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'padding': '8px 16px',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'gap': '12px',
            'flexWrap': 'wrap',
        },
        'chart_area': {
            'flex': 1,
            'padding': '0',
            'overflow': 'hidden',
        },
        'right_panel': {
            'width': '320px',
            'minWidth': '320px',
            'backgroundColor': theme['bg_secondary'],
            'borderLeft': f'1px solid {theme["border_primary"]}',
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden',
        },
        'panel_header': {
            'padding': '8px 10px',
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
        },
        'panel_title': {
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'color': theme['text_primary'],
        },
        'panel_content': {
            'flex': 1,
            'overflow': 'auto',
            'padding': '10px',
        },
        'card': {
            'backgroundColor': theme['bg_tertiary'],
            'borderRadius': BORDER_RADIUS['md'],
            'border': f'1px solid {theme["border_primary"]}',
            'marginBottom': '8px',
        },
        'card_header': {
            'padding': '8px 12px',
            'borderBottom': f'1px solid {theme["border_secondary"]}',
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'color': theme['text_primary'],
        },
        'card_body': {
            'padding': '10px',
        },
        'input': {
            'backgroundColor': theme['bg_tertiary'],
            'border': f'1px solid {theme["border_primary"]}',
            'borderRadius': BORDER_RADIUS['md'],
            'color': theme['text_primary'],
            'padding': '8px 12px',
            'fontSize': FONT_SIZES['sm'],
            'width': '100%',
        },
        'input_focus': {
            'borderColor': theme['border_focus'],
            'outline': 'none',
        },
        'button_primary': {
            'backgroundColor': theme['accent_blue'],
            'color': '#fff',
            'border': 'none',
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '10px 20px',
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'cursor': 'pointer',
            'transition': 'all 0.2s ease',
        },
        'button_success': {
            'backgroundColor': theme['accent_green'],
            'color': '#fff',
            'border': 'none',
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '10px 20px',
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'cursor': 'pointer',
        },
        'button_outline': {
            'backgroundColor': 'transparent',
            'color': theme['text_secondary'],
            'border': f'1px solid {theme["border_primary"]}',
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '8px 16px',
            'fontSize': FONT_SIZES['sm'],
            'cursor': 'pointer',
        },
        'metric_card': {
            'backgroundColor': theme['bg_tertiary'],
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '8px 10px',
            'marginBottom': '6px',
            'border': f'1px solid {theme["border_primary"]}',
        },
        'metric_label': {
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_primary'],
            'opacity': 0.8,
            'marginBottom': '4px',
        },
        'metric_value': {
            'fontSize': FONT_SIZES['xl'],
            'fontWeight': '600',
            'color': theme['text_primary'],
            'fontFamily': FONT_MONO,
        },
        'metric_positive': {
            'color': theme['accent_green'],
        },
        'metric_negative': {
            'color': theme['accent_red'],
        },
        'checklist_container': {
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '4px',
        },
        'checklist_item': {
            'display': 'flex',
            'alignItems': 'center',
            'padding': '6px 8px',
            'borderRadius': BORDER_RADIUS['sm'],
            'cursor': 'pointer',
            'transition': 'background-color 0.15s ease',
        },
        'status_badge': {
            'display': 'inline-flex',
            'alignItems': 'center',
            'padding': '1px 6px',
            'borderRadius': BORDER_RADIUS['full'],
            'fontSize': '10px',
            'fontWeight': '500',
        },
        'status_success': {
            'backgroundColor': f'{theme["accent_green"]}20',
            'color': theme['accent_green'],
        },
        'status_warning': {
            'backgroundColor': f'{theme["accent_orange"]}20',
            'color': theme['accent_orange'],
        },
        'status_error': {
            'backgroundColor': f'{theme["accent_red"]}20',
            'color': theme['accent_red'],
        },
        'tab_container': {
            'display': 'flex',
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'backgroundColor': theme['bg_secondary'],
        },
        'tab': {
            'padding': '10px 14px',
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'cursor': 'pointer',
            'borderBottom': '2px solid transparent',
            'transition': 'all 0.2s ease',
        },
        'tab_active': {
            'color': theme['text_primary'],
            'borderBottomColor': theme['accent_blue'],
        },
    }


# CSS string for custom styling (animations, hover states, etc.)
CUSTOM_CSS = '''
    /* Animations */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes slideIn {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    @keyframes shimmer {
        0% { background-position: -200% 0; }
        100% { background-position: 200% 0; }
    }
    @keyframes progressBar {
        0% { width: 0%; }
        100% { width: 100%; }
    }

    /* Fade-in for results */
    .fade-in {
        animation: fadeIn 0.3s ease-out;
    }
    .slide-in {
        animation: slideIn 0.3s ease-out;
    }

    /* Progress bar */
    .progress-container {
        width: 100%;
        height: 4px;
        background: #21262d;
        border-radius: 2px;
        overflow: hidden;
        margin: 8px 0;
    }
    .progress-bar {
        height: 100%;
        background: linear-gradient(90deg, #58a6ff, #3fb950, #58a6ff);
        background-size: 200% 100%;
        animation: shimmer 1.5s linear infinite;
        transition: width 0.3s ease;
    }
    .progress-bar.indeterminate {
        width: 100%;
        animation: shimmer 1s linear infinite;
    }

    /* Metric cards animation */
    .metric-card-animated {
        animation: fadeIn 0.4s ease-out;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card-animated:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }

    /* Dark theme dropdown */
    .dark-dropdown .Select-control {
        background-color: #21262d !important;
        border-color: #30363d !important;
        transition: border-color 0.2s ease !important;
    }
    .dark-dropdown .Select-control:hover {
        border-color: #58a6ff !important;
    }
    .dark-dropdown .Select-menu-outer {
        background-color: #21262d !important;
        border-color: #30363d !important;
        animation: fadeIn 0.15s ease-out;
    }
    .dark-dropdown .Select-option {
        background-color: #21262d !important;
        color: #e6edf3 !important;
        transition: background-color 0.15s ease !important;
    }
    .dark-dropdown .Select-option:hover {
        background-color: #30363d !important;
    }
    .dark-dropdown .Select-value-label {
        color: #e6edf3 !important;
    }
    .dark-dropdown .Select-placeholder {
        color: #8b949e !important;
    }

    /* Date picker dark theme */
    .SingleDatePickerInput {
        background-color: #21262d !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
        transition: border-color 0.2s ease !important;
    }
    .SingleDatePickerInput:hover {
        border-color: #58a6ff !important;
    }
    .DateInput_input {
        background-color: #21262d !important;
        color: #e6edf3 !important;
        font-size: 14px !important;
        padding: 8px 12px !important;
    }
    .CalendarDay__selected {
        background: #58a6ff !important;
        border-color: #58a6ff !important;
    }

    /* Panel tabs */
    .panel-tab {
        background: transparent !important;
        transition: all 0.2s ease !important;
        position: relative;
    }
    .panel-tab:hover {
        background-color: #21262d !important;
    }
    .panel-tab.active {
        border-bottom-color: #58a6ff !important;
        color: #e6edf3 !important;
    }

    /* Tab indicator animation */
    .panel-tab::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 50%;
        width: 0;
        height: 2px;
        background: #58a6ff;
        transition: all 0.3s ease;
        transform: translateX(-50%);
    }
    .panel-tab.active::after {
        width: 100%;
    }

    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #161b22;
    }
    ::-webkit-scrollbar-thumb {
        background: #30363d;
        border-radius: 4px;
        transition: background 0.2s ease;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #484f58;
    }

    /* Loading spinner */
    ._dash-loading {
        background-color: transparent !important;
    }

    /* Checkbox styling */
    input[type="checkbox"] {
        accent-color: #58a6ff;
        cursor: pointer;
        transition: transform 0.1s ease;
    }
    input[type="checkbox"]:hover {
        transform: scale(1.1);
    }

    /* Button hover states */
    button {
        transition: all 0.2s ease !important;
    }
    button:hover {
        opacity: 0.9;
        transform: translateY(-1px);
    }
    button:active {
        transform: translateY(1px);
    }

    /* Alert styles */
    .custom-alert {
        animation: slideIn 0.3s ease-out;
        border-left: 4px solid;
        border-radius: 6px;
    }
    .custom-alert.success {
        background: rgba(63, 185, 80, 0.1);
        border-left-color: #3fb950;
    }
    .custom-alert.warning {
        background: rgba(210, 153, 34, 0.1);
        border-left-color: #d29922;
    }
    .custom-alert.error {
        background: rgba(248, 81, 73, 0.1);
        border-left-color: #f85149;
    }

    /* Tooltip styling */
    .tooltip-inner {
        background-color: #21262d !important;
        border: 1px solid #30363d !important;
        color: #e6edf3 !important;
        font-size: 12px !important;
        padding: 8px 12px !important;
        max-width: 250px !important;
    }
    .tooltip.bs-tooltip-top .tooltip-arrow::before,
    .tooltip.bs-tooltip-bottom .tooltip-arrow::before {
        border-top-color: #30363d !important;
        border-bottom-color: #30363d !important;
    }

    /* Card hover effect */
    .card-hover {
        transition: all 0.2s ease;
    }
    .card-hover:hover {
        border-color: #58a6ff;
        box-shadow: 0 0 0 1px #58a6ff;
    }

    /* Status badge pulse for loading */
    .status-loading {
        animation: pulse 1.5s ease-in-out infinite;
    }

    /* Smooth chart transitions */
    .js-plotly-plot .plotly .main-svg {
        transition: opacity 0.3s ease;
    }

    /* Resizable chart container */
    .resizable-chart {
        resize: vertical;
        overflow: auto;
        min-height: 400px;
        max-height: calc(100vh - 120px);
        position: relative;
    }
    .resizable-chart::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        width: 60px;
        height: 6px;
        background: linear-gradient(to bottom, transparent, #30363d);
        border-radius: 0 0 3px 3px;
        pointer-events: none;
    }
    .resizable-chart::-webkit-resizer {
        background: #30363d;
        border-radius: 0 0 6px 0;
    }

    /* Chart library toggle */
    #chart-library-toggle label {
        cursor: pointer;
        transition: color 0.2s ease;
    }
    #chart-library-toggle input {
        margin-right: 6px;
    }

    /* TradingView container */
    #tv-chart-container {
        display: flex;
        flex-direction: column;
    }

    /* Signal tabs */
    .signal-tabs .tab {
        border: none !important;
        background: transparent !important;
        padding: 6px 10px !important;
    }
    .signal-tabs .tab--selected {
        border: none !important;
        background: transparent !important;
    }

    /* Compact accordion for stacked panels */
    .compact-accordion .accordion-item {
        background: transparent !important;
        border: none !important;
        margin-bottom: 4px;
    }
    .compact-accordion .accordion-button {
        padding: 6px 8px !important;
        font-size: 11px !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px !important;
        text-transform: uppercase !important;
        background: transparent !important;
        color: #c9d1d9 !important;
        box-shadow: none !important;
    }
    .compact-accordion .accordion-button:not(.collapsed) {
        background: transparent !important;
        color: #e6edf3 !important;
        box-shadow: none !important;
    }
    .compact-accordion .accordion-button::after {
        transform: scale(0.8);
        background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='%23e6edf3'%3e%3cpath fill-rule='evenodd' d='M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z'/%3e%3c/svg%3e");
    }
    .compact-accordion .accordion-body {
        padding: 6px 8px 8px !important;
    }
    .compact-accordion .accordion-title-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        width: 100%;
    }
    .compact-accordion .accordion-title-summary {
        font-size: 10px;
        font-weight: 500;
        color: #8b949e;
        text-transform: none;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 180px;
    }
    .compact-accordion .accordion-title-summary--signals {
        max-width: 320px;
        white-space: normal;
        line-height: 1.2;
    }

    /* Strategy Mode Radio Cards */
    .strategy-mode-radio {
        display: flex;
        flex-direction: column;
        gap: 0;
    }
    .strategy-mode-radio label {
        display: block !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .strategy-mode-radio input[type="radio"] {
        display: none !important;
    }
    .strategy-mode-card {
        transition: all 0.2s ease !important;
    }
    .strategy-mode-card:hover {
        border-color: #58a6ff !important;
        background-color: #21262d !important;
    }
    .strategy-mode-radio input[type="radio"]:checked + .strategy-mode-card,
    .strategy-mode-radio label:has(input:checked) .strategy-mode-card {
        border-color: #58a6ff !important;
        background-color: rgba(88, 166, 255, 0.1) !important;
        box-shadow: 0 0 0 1px rgba(88, 166, 255, 0.3) !important;
    }

    /* Signal checklist text visibility */
    #buy-signals label,
    #sell-signals label {
        color: #e6edf3 !important;
    }
    #buy-signals span,
    #sell-signals span {
        color: #e6edf3 !important;
    }

    /* Unified BUY/SELL signal list */
    .signals-unified-header {
        display: grid;
        grid-template-columns: 36px 1fr 36px;
        align-items: center;
        gap: 6px;
        padding: 4px 8px 6px;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        text-align: center;
        position: sticky;
        top: 0;
        z-index: 1;
        background-color: #161b22;
        border-bottom: 1px solid #30363d;
    }
    .signals-unified-header span {
        justify-self: center;
    }
    .signals-unified-controls {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 4px 2px 6px;
    }
    .signals-unified-controls input {
        font-size: 11px !important;
        padding: 6px 8px !important;
    }
    .signals-category-filter {
        display: flex;
        flex-wrap: wrap;
        gap: 6px 10px;
        font-size: 10px;
        color: #8b949e;
    }
    .signals-category-filter label {
        margin: 0 !important;
        cursor: pointer;
    }
    .signals-unified-list {
        max-height: 264px;
        overflow-y: auto;
        border: 1px solid #30363d;
        border-radius: 6px;
        background-color: #161b22;
        padding: 4px 6px;
    }
    .signal-row {
        display: grid;
        grid-template-columns: 36px 1fr 36px;
        align-items: center;
        gap: 6px;
        padding: 4px 2px;
        border-radius: 4px;
    }
    .signal-row:nth-child(odd) {
        background-color: rgba(48, 54, 61, 0.2);
    }
    .signal-name {
        font-size: 11px;
        color: #e6edf3;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        text-align: center;
        justify-self: center;
    }
    .signal-toggle label {
        display: flex !important;
        justify-content: center;
        margin: 0 !important;
        cursor: pointer;
    }
    .signal-toggle input {
        margin: 0 !important;
    }
    .signal-toggle span {
        display: none;
    }
    .signal-toggle-placeholder {
        height: 16px;
    }

    /* Signal logic toggle visibility */
    .signal-logic-toggle label {
        color: #e6edf3 !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.3px !important;
    }
'''
