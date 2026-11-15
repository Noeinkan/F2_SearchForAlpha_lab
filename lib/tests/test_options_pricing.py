"""Numerical and contract checks for the manual options calculator."""

import json
import math

import pytest
from typer.testing import CliRunner

from lib.cli.app import app
from lib.dash.routes import build_options_path, is_options_route, parse_path
from lib.options.pricing import Leg, payoff_at, payoff_summary, price_option


def test_textbook_call_and_put_parity():
    call = price_option(spot=100, strike=100, days=365, iv=.2, rate=.05)
    put = price_option(spot=100, strike=100, days=365, iv=.2, rate=.05, kind='put')
    assert call['value'] == pytest.approx(10.4505835722, abs=1e-8)
    assert call['value'] - put['value'] == pytest.approx(100 - 100 * math.exp(-.05))
    assert call['delta'] == pytest.approx(.6368306512, abs=1e-8)
    assert call['gamma'] == pytest.approx(.0187620173, abs=1e-8)


def test_greeks_match_finite_differences():
    args = dict(spot=100, strike=105, days=90, iv=.3, rate=.04, yield_rate=.01)
    base = price_option(**args)
    up = price_option(**{**args, 'spot': 100.01})['value']
    down = price_option(**{**args, 'spot': 99.99})['value']
    assert (up - down) / .02 == pytest.approx(base['delta'], rel=1e-5)
    assert (up - 2 * base['value'] + down) / .0001 == pytest.approx(base['gamma'], rel=1e-4)
    iv_up = price_option(**{**args, 'iv': .3001})['value']
    assert (iv_up - base['value']) / .01 == pytest.approx(base['vega'], rel=1e-3)


def test_exact_payoff_summary_for_call_and_spread():
    call = [Leg(1, 'call', 100, 5)]
    assert payoff_at(105, call) == 0
    assert payoff_summary(call) == {'break_evens': [105.0], 'max_profit': None, 'max_loss': -500.0}
    spread = [Leg(1, 'call', 100, 8), Leg(-1, 'call', 110, 3)]
    assert payoff_summary(spread) == {'break_evens': [105.0], 'max_profit': 500.0, 'max_loss': -500.0}


def test_expiry_and_invalid_inputs():
    assert price_option(spot=110, strike=100, days=0, iv=.2)['value'] == 10
    assert price_option(spot=110, strike=100, days=0, iv=.2)['gamma'] is None
    with pytest.raises(ValueError):
        price_option(spot=-1, strike=100, days=30, iv=.2)
    with pytest.raises(ValueError):
        payoff_summary([Leg(1, 'call', 100, float('nan'))])


def test_cli_json_and_route():
    result = CliRunner().invoke(app, ['options', 'price', '--spot', '100', '--strike', '100',
                                     '--days', '365', '--iv', '0.2', '--json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)['value'] == pytest.approx(10.4505835722)
    assert build_options_path('TSLA') == '/options/TSLA'
    assert is_options_route('/options/TSLA')
    assert parse_path('/options/tsla') == ('options', 'TSLA')
