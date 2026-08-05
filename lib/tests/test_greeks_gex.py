"""Tests for Black-Scholes Greeks and estimated GEX/DEX ladders."""

from __future__ import annotations

from datetime import date

from lib.options.greeks import (
    ALL_EXPIRIES_KEY,
    aggregate_gex_ladder,
    bs_delta,
    bs_gamma,
    build_gex_ladders,
    gex_levels,
    merge_gex_ladders,
)
from scripts.flow_scanner import Contract


def _contract(
    strike: float,
    cp: str,
    oi: int,
    vol: int = 0,
    *,
    expiry: date = date(2026, 9, 18),
    iv: float = 0.25,
) -> Contract:
    return Contract(
        ticker="TEST",
        expiry=expiry,
        strike=strike,
        cp=cp,  # type: ignore[arg-type]
        last=1.0,
        bid=0.9,
        ask=1.1,
        volume=vol,
        open_interest=oi,
        iv=iv,
    )


def test_bs_gamma_atm_positive():
    g = bs_gamma(100.0, 100.0, 30 / 365.0, 0.25)
    assert g > 0


def test_bs_gamma_zero_on_bad_inputs():
    assert bs_gamma(100.0, 100.0, 0.0, 0.25) == 0.0
    assert bs_gamma(100.0, 100.0, 0.1, 0.0) == 0.0
    assert bs_gamma(0.0, 100.0, 0.1, 0.25) == 0.0


def test_bs_delta_call_put_signs():
    T = 30 / 365.0
    call_d = bs_delta(100.0, 100.0, T, 0.25, call=True)
    put_d = bs_delta(100.0, 100.0, T, 0.25, call=False)
    assert 0 < call_d < 1
    assert -1 < put_d < 0


def test_aggregate_put_gex_opposite_call():
    as_of = date(2026, 6, 1)
    expiry = date(2026, 9, 18)
    call = _contract(100.0, "C", oi=500, expiry=expiry)
    put = _contract(100.0, "P", oi=500, expiry=expiry)
    ladder = aggregate_gex_ladder([call, put], spot=100.0, as_of=as_of)
    assert len(ladder) == 1
    row = ladder[0]
    assert row["call_gex"] > 0
    assert row["put_gex"] < 0
    assert abs(row["call_gex"] + row["put_gex"] - row["net_gex"]) < 1e-6


def test_gex_levels_pick_expected_strikes():
    ladder = [
        {
            "strike": 90.0,
            "net_gex": -10.0,
            "call_gex": 1.0,
            "put_gex": -50.0,
            "net_dex": -5.0,
            "call_vol": 10,
            "put_vol": 200,
            "total_oi": 100,
        },
        {
            "strike": 100.0,
            "net_gex": 5.0,
            "call_gex": 20.0,
            "put_gex": -15.0,
            "net_dex": 2.0,
            "call_vol": 50,
            "put_vol": 50,
            "total_oi": 100,
        },
        {
            "strike": 110.0,
            "net_gex": 80.0,
            "call_gex": 90.0,
            "put_gex": -10.0,
            "net_dex": 40.0,
            "call_vol": 500,
            "put_vol": 10,
            "total_oi": 200,
        },
    ]
    levels = gex_levels(ladder, spot=100.0)
    assert levels["call_resistance"] == 110.0
    assert levels["put_support"] == 90.0
    assert levels["hvl"] == 110.0


def test_merge_and_build_all_expiries():
    e1 = date(2026, 7, 17)
    e2 = date(2026, 8, 21)
    contracts = [
        _contract(100.0, "C", oi=100, vol=10, expiry=e1),
        _contract(100.0, "P", oi=80, vol=5, expiry=e1),
        _contract(105.0, "C", oi=200, vol=40, expiry=e2),
        _contract(95.0, "P", oi=150, vol=30, expiry=e2),
    ]
    ladders, meta = build_gex_ladders(contracts, spot=100.0, as_of=date(2026, 6, 1))
    assert e1.isoformat() in ladders
    assert e2.isoformat() in ladders
    assert ALL_EXPIRIES_KEY in ladders
    assert ALL_EXPIRIES_KEY in meta

    dated = {k: v for k, v in ladders.items() if k != ALL_EXPIRIES_KEY}
    merged = merge_gex_ladders(dated)
    by_strike = {r["strike"]: r for r in ladders[ALL_EXPIRIES_KEY]}
    for row in merged:
        assert abs(by_strike[row["strike"]]["net_gex"] - row["net_gex"]) < 1e-6

    assert meta[ALL_EXPIRIES_KEY]["call_resistance"] is not None
    assert "net_gex_total" in meta[ALL_EXPIRIES_KEY]
