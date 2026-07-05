"""
Optimization callbacks.
"""

import pandas as pd
from dash import html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.components import build_alert, build_progress_bar
from lib.dash.dash_config import FONT_SIZES, get_theme
from lib.dash.helpers import (
    extract_signals,
    generate_signal_combinations,
    evaluate_signal_combination,
    compute_robustness_scores,
)
from lib.dash.state import dashboard_state
from lib.dash.callbacks.shared import (
    OPTIMIZATION_BATCH_SIZE,
    _create_best_strategy_highlight,
    _create_optimization_table,
    _create_optimization_table_mini,
)


def register_optimization_callbacks(app) -> None:
    @app.callback(
        [Output('preview-buy-count', 'children'),
         Output('preview-sell-count', 'children'),
         Output('preview-combo-count', 'children')],
        [Input('data-loaded-store', 'data'),
         Input('max-signals-slider', 'value'),
         Input('max-combos-input', 'value')]
    )
    def update_signal_preview(data_loaded, max_signals, max_combos):
        """Show preview of available signals and estimated combinations."""
        if not data_loaded or dashboard_state.df is None:
            return "0", "0", "0"

        df = dashboard_state.df
        buy_signals, sell_signals = extract_signals(df)

        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        actual_combos = min(len(combinations), max_combos or 100)

        return str(len(buy_signals)), str(len(sell_signals)), str(actual_combos)

    @app.callback(
        [Output('optimization-state', 'data'),
         Output('optimization-interval', 'disabled'),
         Output('optimization-progress', 'children'),
         Output('run-optimization-btn', 'disabled'),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True)],
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value'),
         State('min-trades-input', 'value'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def start_optimization(n_clicks, initial_capital, max_signals, max_combos, min_trades, current_state):
        """Initialize optimization run and enable interval for progress updates."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        df = dashboard_state.df

        if df is None:
            return (
                current_state,
                True,
                build_alert("Please load market data first", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        buy_signals, sell_signals = extract_signals(df)
        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        combinations = combinations[:max_combos]

        if not combinations:
            return (
                current_state,
                True,
                build_alert("No valid signal combinations found", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        # Convert tuples to lists for JSON serialization
        combinations_serializable = [[list(buy), list(sell)] for buy, sell in combinations]

        # Reset state in dashboard_state
        dashboard_state.reset_optimization()
        dashboard_state.update_optimization_state(
            running=True,
            total_combinations=len(combinations),
            combinations=combinations_serializable,
            initial_capital=initial_capital,
            min_trades=min_trades or 10,
        )

        new_state = {
            'running': True,
            'current_index': 0,
            'total_combinations': len(combinations),
            'completed': False,
            'sort_by': 'Robustness_Score',
            'sort_ascending': False,
            'min_trades': min_trades or 10,
        }

        progress_ui = html.Div([
            build_progress_bar(0, f"Testing 0/{len(combinations)} combinations...", theme=theme),
            html.Div("Starting optimization...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        return (
            new_state,
            False,  # Enable interval
            progress_ui,
            True,   # Disable button
            html.Div(),  # Clear previous results
            {'display': 'none'}  # Hide apply button
        )

    @app.callback(
        [Output('optimization-state', 'data', allow_duplicate=True),
         Output('optimization-progress', 'children', allow_duplicate=True),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('optimization-interval', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'disabled', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data')],
        [Input('optimization-interval', 'n_intervals')],
        [State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def process_optimization_batch(n_intervals, state):
        """Process a batch of combinations on each interval tick."""
        theme = get_theme()

        if not state or not state.get('running'):
            raise PreventUpdate

        df = dashboard_state.df
        if df is None:
            raise PreventUpdate

        opt_state = dashboard_state.optimization_state
        current_idx = opt_state.get('current_index', 0)
        total = opt_state.get('total_combinations', 0)
        combinations = opt_state.get('combinations', [])
        results = opt_state.get('results', [])
        initial_capital = opt_state.get('initial_capital', 10000)

        if not combinations or current_idx >= total:
            raise PreventUpdate

        # Process batch
        end_idx = min(current_idx + OPTIMIZATION_BATCH_SIZE, total)

        for i in range(current_idx, end_idx):
            buy_combo, sell_combo = combinations[i]
            result = evaluate_signal_combination(df, initial_capital, tuple(buy_combo), tuple(sell_combo))
            results.append(result)

        # Update state
        dashboard_state.update_optimization_state(
            current_index=end_idx,
            results=results
        )

        progress_pct = int((end_idx / total) * 100)

        # Check if complete
        if end_idx >= total:
            dashboard_state.update_optimization_state(running=False, completed=True)
            min_trades = opt_state.get('min_trades', 10)

            results_df = pd.DataFrame(results)
            # Drop error rows (no finite return) BEFORE deciding success, so a
            # run where every combo failed shows an honest failure instead of a
            # fake 0% winner.
            if 'Total_Return_%' in results_df.columns:
                results_df = results_df[results_df['Total_Return_%'].notna()]
            else:
                results_df = results_df.iloc[0:0]

            if results_df.empty:
                state['running'] = False
                state['completed'] = True
                first_error = next((r.get('Error') for r in results if r.get('Error')), None)
                msg = "All combinations failed"
                if first_error:
                    msg += f": {first_error}"
                return (
                    state,
                    build_alert(msg, "warning", theme=theme),
                    html.Div(),
                    True,
                    False,
                    {'display': 'none'},
                    []
                )

            results_df = compute_robustness_scores(results_df, min_trades)
            sort_by = state.get('sort_by', 'Robustness_Score')
            if sort_by not in results_df.columns:
                sort_by = 'Robustness_Score'
            # Keep credible (>= min_trades) combinations above low-sample ones,
            # then rank within each group by the chosen metric.
            results_df = results_df.sort_values(
                ['Low_Sample', sort_by],
                ascending=[True, sort_by == 'Max_Drawdown_%'],
            )

            state['running'] = False
            state['completed'] = True

            final_progress = html.Div([
                html.Div([
                    html.Span("\u2713 ", style={'color': theme['accent_green']}),
                    html.Span(f"Completed! Tested {total} combinations",
                             style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
                ]),
                html.Div(
                    f"Ranked from {total} combos \u2014 the more you test, the more likely the top "
                    "result is luck. Re-run the winner on the Backtest tab with real costs, and "
                    "ideally on a different date range.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'],
                           'marginTop': '4px', 'fontStyle': 'italic'}
                ),
            ])

            results_ui = html.Div([
                _create_best_strategy_highlight(results_df.iloc[0], theme),
                _create_optimization_table(results_df.head(10), theme),
            ], className='fade-in')

            return (
                state,
                final_progress,
                results_ui,
                True,   # Disable interval
                False,  # Re-enable button
                {'display': 'block'},  # Show apply button
                results_df.to_dict('records')
            )

        # Still processing - update progress
        state['current_index'] = end_idx

        progress_ui = html.Div([
            build_progress_bar(progress_pct, f"Testing {end_idx}/{total} combinations...", theme=theme),
            html.Div(f"Found {len([r for r in results if 'Total_Return_%' in r])} valid strategies so far...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        # Show partial results (top 5 so far)
        valid_results = [r for r in results if 'Total_Return_%' in r]
        partial_results = html.Div()
        if len(valid_results) >= 5:
            partial_df = pd.DataFrame(valid_results).sort_values('Total_Return_%', ascending=False).head(5)
            partial_results = html.Div([
                html.Div("Top strategies so far:",
                        style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px'}),
                _create_optimization_table_mini(partial_df, theme)
            ], style={'marginTop': '12px'})

        return (
            state,
            progress_ui,
            partial_results,
            False,  # Keep interval enabled
            True,   # Keep button disabled
            {'display': 'none'},
            []
        )

    @app.callback(
        Output('optimization-results', 'children', allow_duplicate=True),
        [Input('sort-metric-dropdown', 'value')],
        [State('optimization-results-store', 'data'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def sort_optimization_results(sort_by, results_data, state):
        """Re-sort results when sort metric changes."""
        if not results_data or not state.get('completed'):
            raise PreventUpdate

        theme = get_theme()
        results_df = pd.DataFrame(results_data)
        if sort_by not in results_df.columns:
            sort_by = 'Robustness_Score' if 'Robustness_Score' in results_df.columns else 'Total_Return_%'

        # Ascending for drawdown (less negative is better), descending for others.
        # Keep credible combinations above low-sample ones regardless of metric.
        ascending = sort_by == 'Max_Drawdown_%'
        sort_cols = ['Low_Sample', sort_by] if 'Low_Sample' in results_df.columns else [sort_by]
        sort_asc = [True, ascending] if 'Low_Sample' in results_df.columns else [ascending]
        results_df = results_df.sort_values(sort_cols, ascending=sort_asc)

        return html.Div([
            _create_best_strategy_highlight(results_df.iloc[0], theme),
            _create_optimization_table(results_df.head(10), theme),
        ], className='fade-in')

    @app.callback(
        [Output('buy-signals', 'value', allow_duplicate=True),
         Output('sell-signals', 'value', allow_duplicate=True),
         Output('tab-backtest', 'n_clicks', allow_duplicate=True)],
        [Input('apply-strategy-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('tab-backtest', 'n_clicks')],
        prevent_initial_call=True
    )
    def apply_best_strategy(n_clicks, results_data, sort_by, current_backtest_clicks):
        """Apply the best strategy from optimization to the backtest panel."""
        if not n_clicks or not results_data:
            raise PreventUpdate

        results_df = pd.DataFrame(results_data)
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        best = results_df.iloc[0]

        # Parse signal strings back to lists
        buy_signals = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
        sell_signals_str = str(best.get('Sell_Signals', ''))
        sell_signals = [s.strip() for s in sell_signals_str.split(',') if s.strip()]

        # Return values to populate checklists and switch to backtest tab
        return buy_signals, sell_signals, (current_backtest_clicks or 0) + 1
