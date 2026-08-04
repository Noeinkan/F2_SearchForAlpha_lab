"""Optimizer LEARN modal: beginner walkthrough for grid search and related tools."""

from __future__ import annotations

from dash import callback_context
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.optimizer_view import render_optimizer_learn_content


def register_optimizer_help_callbacks(app) -> None:
    @app.callback(
        Output("optimizer-learn-modal", "is_open"),
        Output("optimizer-learn-modal-body", "children"),
        Input("optimizer-learn-button", "n_clicks"),
        Input("optimizer-learn-close", "n_clicks"),
        State("optimizer-learn-modal", "is_open"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_optimizer_learn_modal(_learn, _close, is_open, theme_name):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        theme = get_theme(theme_name or DEFAULT_THEME)
        body = render_optimizer_learn_content(theme)
        if trigger == "optimizer-learn-button":
            return (not bool(is_open)), body
        if trigger == "optimizer-learn-close":
            return False, body
        raise PreventUpdate
