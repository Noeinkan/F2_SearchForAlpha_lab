"""
The order model reaching the three surfaces roadmap 3.7.7 names.

The engine having limit and stop orders is worth nothing if the only way to ask
for one is a Python keyword argument. This module checks the three places a user
or an optimizer can actually reach them from:

* the **backtest toolbar** — four controls, translated into engine kwargs;
* the **optimizer**, which takes those same controls when realistic ranking is
  on and ignores them when it is off;
* the **shared execution search space**, so a sweep can vary the order type the
  way it varies a stop distance.

Each test asserts the wiring, not the arithmetic — :mod:`lib.tests.test_orders`
owns the fill rules. What matters here is that nothing silently drops a setting
on the way to :func:`lib.strategy.backtest`, and that every default reproduces
the engine's pre-3.7 behaviour.
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.dash.callbacks.backtest import _order_model_kwargs  # noqa: E402
from lib.dash.callbacks.optimization import build_eval_kwargs  # noqa: E402
from lib.execution_params import (  # noqa: E402
    EXECUTION_PARAM_KEYS,
    ORDER_PARAM_KEYS,
    ORDER_SEARCH_SPACE,
    load_execution_search_space,
    partition_params,
)
from lib.orders import ORDER_TYPES, TIME_IN_FORCE  # noqa: E402
from lib.strategy import backtest  # noqa: E402


# --------------------------------------------------------------------------- #
# The toolbar
# --------------------------------------------------------------------------- #

class TestToolbarTranslation:
    def test_an_untouched_toolbar_reproduces_the_pre_3_7_engine(self):
        kwargs = _order_model_kwargs('market', 0.2, 'gtc', 'close')
        assert kwargs['order_type'] == 'market'
        assert kwargs['trailing_stop_orders'] is False
        assert kwargs['use_brackets'] is False

    def test_blank_controls_fall_back_to_market_rather_than_erroring(self):
        """A store that predates these controls hands back None for all four."""
        kwargs = _order_model_kwargs(None, None, None, None)
        assert kwargs['order_type'] == 'market'
        assert kwargs['time_in_force'] == 'gtc'
        assert kwargs['limit_offset_pct'] == 0.0
        assert kwargs['trailing_stop_orders'] is False
        assert kwargs['use_brackets'] is False

    def test_one_offset_control_drives_both_engine_offsets(self):
        kwargs = _order_model_kwargs('limit', 0.5, 'gtc', 'close')
        assert kwargs['limit_offset_pct'] == pytest.approx(0.005)
        assert kwargs['stop_offset_pct'] == pytest.approx(0.005)

    def test_exit_handling_picks_exactly_one_mechanism(self):
        stop_order = _order_model_kwargs('market', 0.2, 'gtc', 'stop_order')
        assert stop_order['trailing_stop_orders'] is True
        assert stop_order['use_brackets'] is False

        bracket = _order_model_kwargs('market', 0.2, 'gtc', 'bracket')
        assert bracket['use_brackets'] is True
        # A bracket's legs are fixed at entry — trailing it would make it
        # something else, so the toolbar keeps the two exclusive.
        assert bracket['trailing_stop_orders'] is False

    def test_the_bracket_reuses_the_distances_already_on_screen(self):
        """No bracket-specific inputs, so the engine must default them."""
        kwargs = _order_model_kwargs('market', 0.2, 'gtc', 'bracket')
        assert 'bracket_stop_pct' not in kwargs
        assert 'bracket_target_pct' not in kwargs

    @pytest.mark.parametrize('kind', ORDER_TYPES)
    @pytest.mark.parametrize('tif', TIME_IN_FORCE)
    def test_every_toolbar_choice_is_a_kwarg_the_engine_accepts(self, kind, tif):
        kwargs = _order_model_kwargs(kind, 1.0, tif, 'close')
        signature = inspect.signature(backtest).parameters
        for key in kwargs:
            assert key in signature, f"{key} is not a backtest() parameter"


class TestToolbarControlsExist:
    """The callback's State ids have to be real components or Dash never fires."""

    def test_the_four_order_controls_are_in_the_layout(self):
        from lib.dash.dash_config import get_theme
        from lib.dash.layout.backtest_panel import _create_backtest_panel
        from lib.dash.styles import get_styles

        theme = get_theme()
        rendered = str(_create_backtest_panel(get_styles(theme), theme))
        for control_id in ('order-type', 'order-offset-pct', 'order-tif', 'exit-order-mode'):
            assert f"id='{control_id}'" in rendered, control_id


# --------------------------------------------------------------------------- #
# The optimizer
# --------------------------------------------------------------------------- #

class TestOptimizerWiring:
    def test_idealized_ranking_ignores_the_order_model_entirely(self):
        assert build_eval_kwargs(False, order_type='limit', exit_order_mode='bracket') == {}

    def test_realistic_ranking_carries_the_order_model_through(self):
        kwargs = build_eval_kwargs(
            True,
            strategy_mode='trading',
            min_holding_period=3,
            trailing_stop_pct=10,
            stop_mode='percent',
            fx_fee_pct=0.15,
            slippage_pct=0.05,
            commission_pct=0.1,
            order_type='limit',
            order_offset_pct=0.4,
            order_tif='ioc',
            exit_order_mode='bracket',
        )
        assert kwargs['order_type'] == 'limit'
        assert kwargs['limit_offset_pct'] == pytest.approx(0.004)
        assert kwargs['time_in_force'] == 'ioc'
        assert kwargs['use_brackets'] is True
        # And the cost keys it always carried are still there.
        assert kwargs['commission_per_trade'] == pytest.approx(0.001)

    def test_realistic_ranking_without_the_controls_stays_on_market_orders(self):
        """Older callers pass only the cost arguments; they must not change."""
        kwargs = build_eval_kwargs(
            True, strategy_mode='trading', min_holding_period=3,
            trailing_stop_pct=10, stop_mode='percent',
        )
        assert kwargs['order_type'] == 'market'
        assert kwargs['use_brackets'] is False
        assert kwargs['trailing_stop_orders'] is False

    def test_every_key_it_emits_is_one_the_engine_accepts(self):
        kwargs = build_eval_kwargs(
            True, strategy_mode='trading', order_type='stop_limit', order_tif='day',
            exit_order_mode='stop_order',
        )
        signature = inspect.signature(backtest).parameters
        # strategy_mode et al. go through run_backtest, which forwards them.
        from lib.strategy import run_backtest

        forwarded = inspect.signature(run_backtest).parameters
        for key in kwargs:
            assert key in signature or key in forwarded, key


# --------------------------------------------------------------------------- #
# The shared execution search space
# --------------------------------------------------------------------------- #

class TestSearchSpace:
    def test_the_order_keys_are_all_execution_keys(self):
        assert ORDER_PARAM_KEYS <= EXECUTION_PARAM_KEYS

    def test_partitioning_routes_them_to_backtest_and_not_to_the_indicators(self):
        parted = partition_params({
            'rsi_window': 14,
            'order_type': 'limit',
            'limit_offset_pct': 0.004,
            'time_in_force': 'ioc',
            'use_brackets': True,
        })
        assert parted.indicator_params == {'rsi_window': 14}
        assert parted.backtest_kwargs == {
            'order_type': 'limit',
            'limit_offset_pct': 0.004,
            'time_in_force': 'ioc',
            'use_brackets': True,
        }

    def test_the_shipped_grid_sweeps_the_order_type(self):
        space = load_execution_search_space()
        assert 'order_type' in space, (
            'order_type must be sweepable from the shared grid — see 3.7.7'
        )
        assert set(space['order_type']['choices']) <= set(ORDER_TYPES)

    def test_the_shipped_grid_does_not_sweep_knobs_most_trials_ignore(self):
        """Offsets mean nothing to a market order; sweeping them wastes trials."""
        space = load_execution_search_space()
        assert 'limit_offset_pct' not in space
        assert 'bracket_stop_pct' not in space

    def test_the_opt_in_order_space_is_complete_and_valid(self):
        assert set(ORDER_SEARCH_SPACE) <= ORDER_PARAM_KEYS
        assert set(ORDER_SEARCH_SPACE['order_type']['choices']) == set(ORDER_TYPES)
        assert set(ORDER_SEARCH_SPACE['time_in_force']['choices']) == set(TIME_IN_FORCE)
