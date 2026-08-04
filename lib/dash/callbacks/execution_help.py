"""
Execution Type explainer: modal, sandbox, predict-then-reveal, progress.

The modal body is re-rendered on every interaction (same approach as
``toggle_flow_learn_modal``) so it always picks up the live theme and the live
engine output rather than a cached snapshot.
"""

from dash import ALL, ctx, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.execution_glossary import MODE_ORDER, MODE_SPECS
from lib.dash.execution_view import render_execution_learn_content, render_mode_preview

_DEFAULT_STATE = {'mode': 'trading', 'guess': None, 'revealed': False, 'params': {}}


def _clean_state(data) -> dict:
    """Tolerate a missing or half-written store without blowing up a render."""
    state = {**_DEFAULT_STATE, **(data or {})}
    if state.get('mode') not in MODE_ORDER:
        state['mode'] = 'trading'
    if not isinstance(state.get('params'), dict):
        state['params'] = {}
    return state


def register_execution_help_callbacks(app) -> None:

    # ----------------------------------------------------------------------- #
    # Inline previews under each mode card
    # ----------------------------------------------------------------------- #
    @app.callback(
        [Output(f'preview-mode-{mode}', 'children') for mode in MODE_ORDER],
        [Input('initial-capital', 'value'),
         Input('kelly-win-rate', 'value'),
         Input('kelly-win-loss-ratio', 'value'),
         Input('position-scaling-pct', 'value'),
         Input('amount-per-buy', 'value'),
         Input('position-size-pct', 'value')],
        [State('theme-store', 'data')],
    )
    def update_mode_previews(capital, kelly_win_rate, kelly_win_loss_ratio,
                             position_scaling_pct, amount_per_buy, position_size_pct,
                             theme_name):
        """Keep the dollar preview on each card true to the current settings.

        This is the line that would have prevented the original confusion: it
        states what the first buy signal actually does, in dollars, before
        anything is run.
        """
        theme = get_theme(theme_name or DEFAULT_THEME)
        shared = {
            'capital': capital,
            'kelly_win_rate': kelly_win_rate,
            'kelly_win_loss_ratio': kelly_win_loss_ratio,
            'position_scaling_pct': position_scaling_pct,
            'amount_per_buy': amount_per_buy,
            'position_size_pct': position_size_pct,
        }
        return [render_mode_preview(theme, mode, **shared) for mode in MODE_ORDER]

    # ----------------------------------------------------------------------- #
    # Dead-config warning: sell signals selected while in Accumulation
    # ----------------------------------------------------------------------- #
    @app.callback(
        Output('accumulation-sell-warning', 'children'),
        [Input('strategy-mode', 'value'),
         Input('sell-signals', 'value')],
        [State('theme-store', 'data')],
    )
    def warn_about_ignored_sell_signals(strategy_mode, sell_signals, theme_name):
        if strategy_mode != 'accumulation' or not sell_signals:
            return None
        theme = get_theme(theme_name or DEFAULT_THEME)
        count = len(sell_signals)
        return html.Div(
            f"{count} sell signal{'s' if count != 1 else ''} selected, but "
            f"Accumulation discards them. Switch to Trading or Rebalancing to "
            f"act on sells.",
            className='sfa-exec-warning',
            style={'borderColor': theme['accent_orange'], 'color': theme['accent_orange']},
        )

    # ----------------------------------------------------------------------- #
    # Modal open / close
    # ----------------------------------------------------------------------- #
    @app.callback(
        [Output('execution-learn-modal', 'is_open'),
         Output('execution-learn-state', 'data', allow_duplicate=True)],
        [Input('execution-learn-button', 'n_clicks'),
         Input('help-strategy-mode', 'n_clicks'),
         *[Input(f'help-strategy-{mode}', 'n_clicks') for mode in MODE_ORDER],
         Input('execution-learn-close', 'n_clicks')],
        [State('execution-learn-modal', 'is_open'),
         State('execution-learn-state', 'data'),
         State('strategy-mode', 'value')],
        prevent_initial_call=True,
    )
    def toggle_execution_learn_modal(_btn, _help_all, _help_t, _help_a, _help_r,
                                     _close, is_open, state, selected_mode):
        trigger = ctx.triggered_id
        if trigger == 'execution-learn-close':
            return False, no_update

        state = _clean_state(state)

        # A per-mode "?" opens straight onto that mode; the section header "?"
        # and the button open onto whichever mode is currently selected.
        if isinstance(trigger, str) and trigger.startswith('help-strategy-'):
            target = trigger.removeprefix('help-strategy-')
            mode = target if target in MODE_ORDER else (selected_mode or 'trading')
        else:
            mode = selected_mode if selected_mode in MODE_ORDER else state['mode']

        if mode != state['mode']:
            # New mode, fresh question — never show a stale answer.
            state = {**state, 'mode': mode, 'guess': None, 'revealed': False, 'params': {}}

        return (not bool(is_open)) if trigger == 'execution-learn-button' else True, state

    # ----------------------------------------------------------------------- #
    # Sandbox interactions: mode tabs, guesses, reveal, sliders
    # ----------------------------------------------------------------------- #
    @app.callback(
        [Output('execution-learn-state', 'data'),
         Output('execution-explored-store', 'data')],
        [Input({'type': 'exec-mode-tab', 'mode': ALL}, 'n_clicks'),
         Input({'type': 'exec-predict-option', 'mode': ALL, 'index': ALL}, 'n_clicks'),
         Input({'type': 'exec-reveal', 'mode': ALL}, 'n_clicks'),
         Input({'type': 'exec-param', 'mode': ALL, 'name': ALL}, 'value')],
        [State('execution-learn-state', 'data'),
         State('execution-explored-store', 'data')],
        prevent_initial_call=True,
    )
    def update_sandbox_state(_tabs, _options, _reveals, _params, state, explored):
        trigger = ctx.triggered_id
        if not isinstance(trigger, dict):
            raise PreventUpdate

        state = _clean_state(state)
        explored = list(explored or [])
        kind = trigger.get('type')

        if kind == 'exec-mode-tab':
            mode = trigger['mode']
            if mode == state['mode']:
                raise PreventUpdate
            return ({**state, 'mode': mode, 'guess': None, 'revealed': False,
                     'params': {}}, explored)

        if kind == 'exec-predict-option':
            if state['revealed']:
                raise PreventUpdate
            return {**state, 'guess': trigger['index']}, explored

        if kind == 'exec-reveal':
            mode = state['mode']
            if mode not in explored:
                explored.append(mode)
            return {**state, 'revealed': True}, explored

        if kind == 'exec-param':
            # Slider values arrive as a list aligned with the pattern-matching
            # inputs; rebuild the whole param dict so a drag on one control never
            # drops the others.
            params = dict(state['params'])
            for spec, value in zip(ctx.inputs_list[3], _params):
                params[spec['id']['name']] = value
            return {**state, 'params': params}, explored

        raise PreventUpdate

    # ----------------------------------------------------------------------- #
    # Render: one place builds the body, from state + theme + engine
    # ----------------------------------------------------------------------- #
    @app.callback(
        Output('execution-learn-modal-body', 'children'),
        [Input('execution-learn-state', 'data'),
         Input('execution-learn-modal', 'is_open'),
         Input('theme-store', 'data')],
        [State('execution-explored-store', 'data'),
         State('initial-capital', 'value')],
    )
    def render_execution_learn_body(state, is_open, theme_name, explored, capital):
        if not is_open:
            raise PreventUpdate
        state = _clean_state(state)
        theme = get_theme(theme_name or DEFAULT_THEME)
        params = dict(state['params'])
        params.setdefault('capital', capital)
        return render_execution_learn_content(
            theme,
            mode=state['mode'],
            params=params,
            guess=state['guess'],
            revealed=bool(state['revealed']),
            explored=explored or [],
        )
