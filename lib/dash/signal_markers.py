"""Signal trigger resolution shared by the chart payload and the TRIG/REJ pills.

This logic used to exist twice — once inside ``chart_builder._add_signal_traces``
and once as ``_combine_signals_for_counts`` / ``_apply_consecutive_rules_for_counts``
in ``callbacks.shared``. Two copies of a state machine that must agree is a
standing correctness hazard, and they had already drifted: the chart drew nothing
when no signal columns were selected, while the counter still reported totals
from precomputed backtest columns. This module is the single implementation, so
the pills now count exactly what the chart draws.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

SIGNAL_TYPES = ("buy", "sell")


def combine_signals(
    df: pd.DataFrame,
    columns: List[str] | None,
    logic: str = "or",
    window: int = 0,
) -> pd.Series:
    """Reduce several boolean signal columns to one series.

    ``or`` fires when any column fires. ``and`` requires all of them; with a
    positive ``window`` the columns only have to agree *within* that many bars
    rather than on the same bar, which is what lets a slow confirmation
    indicator still line up with a fast trigger.
    """
    if not columns:
        return pd.Series(False, index=df.index)
    valid_cols = [c for c in columns if c in df.columns]
    if not valid_cols:
        return pd.Series(False, index=df.index)
    if logic == "and":
        if window and window > 0:
            windowed = df[valid_cols].rolling(window=window + 1, min_periods=1).max()
            return (windowed > 0).all(axis=1)
        return df[valid_cols].all(axis=1)
    return df[valid_cols].any(axis=1)


def apply_consecutive_rules(
    signal_series: pd.Series,
    mode: str = "scale_in",
    cooldown: int = 0,
) -> Tuple[pd.Series, pd.Series]:
    """Split a signal series into accepted and rejected triggers.

    Modes:
    - ``scale_in``       every bar that fires is accepted (add to the position)
    - ``edge``           only the first bar of a run
    - ``cooldown``       suppress for ``cooldown`` bars after an accepted trigger
    - ``reset_cooldown`` as ``cooldown``, but also require the signal to go
                         false before it can fire again

    Sequential by nature — each decision depends on the ones before it — so this
    stays a Python loop rather than a vectorised expression.
    """
    mode = (mode or "scale_in").lower()
    cooldown = max(0, int(cooldown or 0))
    values = signal_series.values
    accepted = np.zeros(len(signal_series), dtype=bool)
    rejected = np.zeros(len(signal_series), dtype=bool)
    wait_reset = False
    remaining_cooldown = 0

    for idx, is_signal in enumerate(values):
        if mode == "reset_cooldown" and not is_signal:
            wait_reset = False

        if mode == "edge":
            prev = values[idx - 1] if idx > 0 else False
            allow = bool(is_signal) and not bool(prev)
        elif mode == "cooldown":
            allow = bool(is_signal) and remaining_cooldown == 0
        elif mode == "reset_cooldown":
            allow = bool(is_signal) and remaining_cooldown == 0 and not wait_reset
        else:
            allow = bool(is_signal)

        if is_signal and allow:
            accepted[idx] = True
            if mode in ("cooldown", "reset_cooldown") and cooldown > 0:
                remaining_cooldown = cooldown
            if mode == "reset_cooldown":
                wait_reset = True
        elif is_signal and not allow:
            rejected[idx] = True

        if remaining_cooldown > 0:
            remaining_cooldown -= 1

    return (
        pd.Series(accepted, index=signal_series.index),
        pd.Series(rejected, index=signal_series.index),
    )


def resolve_triggers(
    df: pd.DataFrame,
    signal_type: str,
    columns: List[str] | None,
    *,
    logic: str = "or",
    window: int = 0,
    mode: str = "scale_in",
    cooldown: int = 0,
) -> Tuple[pd.Series, pd.Series]:
    """Accepted/rejected masks for one side, honouring backtest columns.

    A completed backtest writes ``Buy_Trigger_Accepted`` / ``Buy_Trigger_Rejected``
    (and the sell equivalents) onto the frame. Those already encode the executed
    consecutive-signal rules, so they win over recomputing here — otherwise the
    chart could disagree with the trades the backtest actually took.
    """
    empty = pd.Series(False, index=df.index)
    if not columns:
        return empty, empty

    accepted_col = f"{signal_type.capitalize()}_Trigger_Accepted"
    rejected_col = f"{signal_type.capitalize()}_Trigger_Rejected"
    if accepted_col in df.columns and rejected_col in df.columns:
        return (
            df[accepted_col].fillna(False).astype(bool),
            df[rejected_col].fillna(False).astype(bool),
        )

    combined = combine_signals(df, columns, logic, window)
    return apply_consecutive_rules(combined, mode, cooldown)


def trigger_counts(
    df: pd.DataFrame,
    selected_signals: List[str] | None,
    buy_columns: List[str] | None,
    sell_columns: List[str] | None,
    *,
    logic: str = "or",
    window: int = 0,
    mode: str = "scale_in",
    cooldown: int = 0,
) -> Dict[str, int]:
    """Total accepted/rejected triggers across the enabled sides."""
    totals = {"accepted": 0, "rejected": 0}
    if df is None or df.empty:
        return totals

    selected = set(selected_signals or [])
    for signal_type, columns in (("buy", buy_columns), ("sell", sell_columns)):
        if signal_type not in selected:
            continue
        accepted, rejected = resolve_triggers(
            df, signal_type, columns,
            logic=logic, window=window, mode=mode, cooldown=cooldown,
        )
        totals["accepted"] += int(accepted.sum())
        totals["rejected"] += int(rejected.sum())

    return totals
