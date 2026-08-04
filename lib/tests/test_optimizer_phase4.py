"""Tests for Optimizer workspace Phase 4 (Bayesian apply, STOP UX, OOS polling)."""

from __future__ import annotations

import threading

import optuna

from lib import bayesian_optimization as bopt
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS
from lib.dash.optimizer_bayesian_apply import merge_indicator_settings_from_params


def test_merge_indicator_settings_from_params():
    merged = merge_indicator_settings_from_params(
        DEFAULT_INDICATOR_SETTINGS,
        {"rsi_window": 21},
    )
    assert merged["rsi"]["period"] == 21
    assert merged["macd"]["fast"] == DEFAULT_INDICATOR_SETTINGS["macd"]["fast"]


def test_make_control_callback_stops_study():
    cancel = threading.Event()
    n_trials = 5

    def progress_callback(done: int, total: int) -> None:
        if done >= 1:
            cancel.set()

    study = optuna.create_study(direction="maximize")
    control_cb = bopt._make_control_callback(
        n_trials,
        cancel_event=cancel,
        progress_callback=progress_callback,
    )

    def objective(trial: optuna.Trial) -> float:
        return trial.suggest_float("x", 0.0, 1.0)

    study.optimize(
        objective,
        n_trials=n_trials,
        callbacks=[control_cb],
        show_progress_bar=False,
    )
    assert len(study.trials) < n_trials


def test_register_callbacks_no_duplicate_output():
    import dash
    import dash_bootstrap_components as dbc

    from lib.dash.callbacks import register_callbacks

    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    register_callbacks(app)
    assert app.callback_map
