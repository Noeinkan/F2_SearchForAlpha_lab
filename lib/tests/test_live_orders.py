"""
Limit, stop and stop-limit orders in the paper runner (ROADMAP 8.11).

Three layers, each against the backtest's order model in lib/orders.py:
    - LiveOrderModel reads live_params, prices orders like the engine does, and
      refuses settings the runner cannot honour;
    - MockBroker works resting orders against later bars with lib.orders' fill model;
    - PaperRunner places, settles, expires (ioc / order_expiry_bars) and replaces them.

No ib_async, no network.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
import typer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.agent_strategy import load_bundle
from lib.engine.steps import signal_order_prices
from lib.live import alerts
from lib.live import runner as runner_module
from lib.live.broker import (
    ORDER_CANCELLED,
    ORDER_FILLED,
    ORDER_REJECTED,
    ORDER_WORKING,
    Bar,
    MockBroker,
    Order,
)
from lib.live.execution import LiveOrderModel, UnsupportedLiveParams, unsupported_live_params
from lib.live.runner import PaperRunner, RunnerOptions
from lib.orders import Bar as BookBar
from lib.orders import Order as BookOrder
from lib.orders import fill_price
from lib.store import fills as fills_store
from lib.store import state as state_store
from lib.store import trials as trials_store

TICKER = "SPY"


def _bar(i: int, o: float, h: float, low: float, c: float) -> Bar:
    return Bar(datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i), o, h, low, c, 1_000_000)


# ---------------------------------------------------------------------------
# LiveOrderModel
# ---------------------------------------------------------------------------


def test_order_and_indicator_keys_are_accepted():
    params = {
        "rsi_window": 14,
        "order_type": "stop_limit",
        "limit_offset_pct": 0.004,
        "time_in_force": "ioc",
        "slippage_pct": 0.001,  # simulated cost; the broker charges the real one
        "trailing_stop_loss": 0,  # explicitly off
        "consecutive_signal_mode": "edge",
    }
    assert unsupported_live_params(params) == {}


@pytest.mark.parametrize(
    "key, value",
    [
        ("trailing_stop_loss", 0.05),
        ("take_profit", 0.1),
        ("use_brackets", True),
        ("trailing_stop_orders", True),
        ("min_holding_period", 5),
        ("cooldown_bars", 3),
        ("consecutive_signal_mode", "scale_in"),
        ("position_size_pct", 100),
        ("amount_per_buy", 5_000),
        ("kelly_win_rate", 0.55),
        ("signal_logic", "and"),
        ("signal_window", 3),
    ],
)
def test_settings_the_runner_cannot_honour_are_refused(key, value):
    with pytest.raises(UnsupportedLiveParams) as info:
        LiveOrderModel.from_live_params({"rsi_window": 14, key: value})
    assert list(info.value.problems) == [key]


def test_bad_order_values_raise():
    with pytest.raises(ValueError, match="order_type"):
        LiveOrderModel.from_live_params({"order_type": "iceberg"})
    with pytest.raises(ValueError, match="time_in_force"):
        LiveOrderModel.from_live_params({"order_type": "limit", "time_in_force": "fok"})


def test_defaults_match_the_backtest():
    model = LiveOrderModel.from_live_params({})
    assert (model.order_type, model.limit_offset, model.stop_offset, model.time_in_force) == (
        "market", 0.002, 0.002, "gtc",
    )
    assert not model.rests


@pytest.mark.parametrize("order_type", ["market", "limit", "stop", "stop_limit"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_prices_are_the_engines(order_type, side):
    model = LiveOrderModel(order_type=order_type, limit_offset=0.003, stop_offset=0.005, price_tick=0)
    assert model.prices(side, 187.43) == signal_order_prices(model, side.lower(), 187.43)


def test_prices_round_to_the_tick_without_asking_for_worse():
    model = LiveOrderModel(order_type="stop_limit", limit_offset=0.001, stop_offset=0.001)
    buy = model.prices("BUY", 100.37)  # stop 100.47037, limit 100.5708...
    sell = model.prices("SELL", 100.37)  # stop 100.26963, limit 100.16936...
    assert buy["stop_price"] == 100.48 and buy["limit_price"] == 100.57
    assert sell["stop_price"] == 100.26 and sell["limit_price"] == 100.17
    assert LiveOrderModel(order_type="limit", limit_offset=0.0).prices("BUY", 100.0)["limit_price"] == 100.0


def test_time_in_force_mapping():
    assert LiveOrderModel(order_type="limit").cancel_after_bars is None
    assert LiveOrderModel(order_type="limit", time_in_force="ioc").cancel_after_bars == 1
    assert LiveOrderModel(order_type="limit", order_expiry_bars=3).cancel_after_bars == 3
    assert LiveOrderModel(order_type="limit", time_in_force="ioc", order_expiry_bars=3).cancel_after_bars == 1
    order = LiveOrderModel(order_type="stop_limit", time_in_force="ioc").broker_order(
        symbol=TICKER, side="buy", quantity=5, close=100, client_order_id="c1"
    )
    assert (order.order_type, order.time_in_force, order.side) == ("STP LMT", "DAY", "BUY")


# ---------------------------------------------------------------------------
# MockBroker resting orders
# ---------------------------------------------------------------------------


async def _broker_at(price: float = 100.0) -> MockBroker:
    broker = MockBroker(starting_cash=100_000)
    await broker.connect()
    await broker.push_bar(TICKER, _bar(0, price, price, price, price))
    return broker


async def test_buy_limit_waits_for_a_later_bar_then_fills_at_the_limit():
    broker = await _broker_at(100.0)
    oid = await broker.place_order(Order(TICKER, "BUY", 10, "LMT", limit_price=99.0))
    assert (await broker.order_status(oid)).status == ORDER_WORKING

    await broker.push_bar(TICKER, _bar(1, 100.5, 101.0, 99.5, 100.0))  # never reaches 99
    assert (await broker.order_status(oid)).status == ORDER_WORKING

    await broker.push_bar(TICKER, _bar(2, 99.8, 100.0, 98.5, 99.5))
    status = await broker.order_status(oid)
    assert (status.status, status.filled_quantity, status.avg_fill_price) == (ORDER_FILLED, 10, 99.0)
    assert (await broker.get_positions())[0].quantity == 10


async def test_buy_limit_opened_through_fills_at_the_open():
    broker = await _broker_at(100.0)
    oid = await broker.place_order(Order(TICKER, "BUY", 10, "LMT", limit_price=99.0))
    await broker.push_bar(TICKER, _bar(1, 97.0, 98.0, 96.0, 97.5))
    assert (await broker.order_status(oid)).avg_fill_price == 97.0


@pytest.mark.parametrize(
    "order, bars",
    [
        (Order(TICKER, "SELL", 10, "STP", stop_price=95.0), [(97, 98, 94, 96), (90, 91, 89, 90)]),
        (Order(TICKER, "BUY", 10, "STP", stop_price=105.0), [(100, 104, 99, 103), (107, 108, 106, 107)]),
        # Gaps past its limit, stays a plain limit, and fills when the range returns.
        (Order(TICKER, "BUY", 10, "STP LMT", stop_price=105.0, limit_price=106.0),
         [(108, 110, 107, 109), (107.5, 108, 105.5, 106.5)]),
    ],
)
async def test_mock_fills_where_lib_orders_would(order, bars):
    broker = await _broker_at(100.0)
    if order.side == "SELL":
        await broker.submit_order(Order(TICKER, "BUY", 10))
    oid = await broker.place_order(order)
    book_order = BookOrder(
        side=order.side.lower(),
        order_type={"STP": "stop", "STP LMT": "stop_limit"}[order.order_type],
        qty=10,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
    )
    expected = None
    for i, (o, h, low, c) in enumerate(bars, start=1):
        book_bar = BookBar(index=i, open=o, high=h, low=low, close=c)
        price = fill_price(book_order, book_bar)
        await broker.push_bar(TICKER, _bar(i, o, h, low, c))
        if price is not None and expected is None:
            expected = price
            break
        if book_order.order_type == "stop_limit" and fill_price(
            dataclasses.replace(book_order, order_type="stop"), book_bar
        ) is not None:
            book_order.triggered = True
    status = await broker.order_status(oid)
    assert status.status == ORDER_FILLED
    assert status.avg_fill_price == expected


async def test_cancel_and_reject():
    broker = await _broker_at(100.0)
    kept = await broker.place_order(Order(TICKER, "BUY", 10, "LMT", limit_price=90.0))
    other = await broker.place_order(Order("QQQ", "BUY", 10, "LMT", limit_price=90.0))
    await broker.cancel_all(TICKER)
    assert (await broker.order_status(kept)).status == ORDER_CANCELLED
    assert (await broker.order_status(other)).status == ORDER_WORKING

    naked = await broker.place_order(Order(TICKER, "SELL", 10, "LMT", limit_price=101.0))
    await broker.push_bar(TICKER, _bar(1, 100, 102, 99, 101))
    status = await broker.order_status(naked)
    assert status.status == ORDER_REJECTED and "insufficient position" in status.message


# ---------------------------------------------------------------------------
# PaperRunner
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    db_path = tmp_path / "orders.db"
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(state_store, "PID_DIR", tmp_path / "running")
    monkeypatch.delenv(alerts.ALERT_WEBHOOK_ENV, raising=False)
    return db_path


class _Sink:
    def __init__(self) -> None:
        self.alerts: list[alerts.Alert] = []

    async def __call__(self, alert: alerts.Alert) -> bool:
        self.alerts.append(alert)
        return True


async def _runner(db_path, name: str, **order_params) -> tuple[PaperRunner, MockBroker, _Sink]:
    base = load_bundle("mean_reversion_rsi_bb")
    bundle = dataclasses.replace(base, ticker=TICKER, live_params={**base.live_params, **order_params})
    broker = MockBroker(starting_cash=100_000)
    sink = _Sink()
    runner = PaperRunner(broker, RunnerOptions(name=name, bundle=bundle, db_path=db_path), alert_sink=sink)
    runner.heartbeat_seconds = 0
    runner.restart_window = None
    await runner.start()
    await broker.push_bar(TICKER, _bar(0, 100, 100, 100, 100))
    return runner, broker, sink


def _row(db_path, name):
    (row,) = fills_store.list_fills(strategy_name=name, db_path=db_path)
    return row


async def test_limit_buy_rests_then_fills_and_is_recorded(isolated):
    runner, broker, _ = await _runner(isolated, "lmt", order_type="limit", limit_offset_pct=0.01)
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))

    working = runner.orders.get("BUY")
    assert working is not None and working.order.limit_price == 99.0
    assert _row(isolated, "lmt")["status"] == "working"
    assert await broker.get_positions() == []

    await broker.push_bar(TICKER, _bar(1, 99.5, 100, 98.8, 99.2))

    assert runner.orders.get("BUY") is None
    row = _row(isolated, "lmt")
    assert (row["status"], row["price"], row["quantity"], row["order_type"]) == ("filled", 99.0, 10, "limit")
    assert row["broker_order_id"]
    assert (await broker.get_positions())[0].quantity == 10


async def test_ioc_gets_one_bar_of_range_then_is_cancelled(isolated):
    runner, broker, _ = await _runner(isolated, "ioc", order_type="limit", limit_offset_pct=0.05, time_in_force="ioc")
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))

    await broker.push_bar(TICKER, _bar(1, 100, 101, 99, 100))  # misses 95

    assert runner.orders.get("BUY") is None
    assert _row(isolated, "ioc")["status"] == "cancelled"
    assert broker._books[TICKER].is_empty


async def test_order_expiry_bars_counts_the_runners_bars(isolated):
    runner, broker, _ = await _runner(isolated, "exp", order_type="limit", limit_offset_pct=0.05, order_expiry_bars=3)
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))
    for i in (1, 2):
        await broker.push_bar(TICKER, _bar(i, 100, 101, 99, 100))
        assert runner.orders.get("BUY") is not None, f"still working after bar {i}"
    await broker.push_bar(TICKER, _bar(3, 100, 101, 99, 100))
    assert runner.orders.get("BUY") is None
    assert _row(isolated, "exp")["status"] == "cancelled"


async def test_new_signal_replaces_the_working_order(isolated):
    runner, broker, _ = await _runner(isolated, "rep", order_type="limit", limit_offset_pct=0.05)
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))
    first = runner.orders.get("BUY")

    assert await runner._replace_working("BUY") is True
    assert (await broker.order_status(first.broker_order_id)).status == ORDER_CANCELLED
    await runner._submit(side="BUY", quantity=10, bar=_bar(1, 100, 100, 100, 100))
    assert runner.orders.get("BUY").client_order_id != first.client_order_id
    statuses = sorted(r["status"] for r in fills_store.list_fills(strategy_name="rep", db_path=isolated))
    assert statuses == ["cancelled", "working"]


async def test_replacing_an_order_that_just_filled_does_not_buy_twice(isolated):
    runner, broker, _ = await _runner(isolated, "race", order_type="limit", limit_offset_pct=0.01)
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))
    broker._work_resting(TICKER, _bar(1, 99, 99, 98, 99))  # filled, but the runner has not seen the bar

    assert await runner._replace_working("BUY") is False
    assert _row(isolated, "race")["status"] == "filled"


async def test_stop_cancels_and_reports_working_orders(isolated):
    runner, broker, _ = await _runner(isolated, "stp", order_type="stop", stop_offset_pct=0.02)
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))
    result = await runner.stop()
    (cancelled,) = result["cancelled_orders"]
    assert (cancelled["order_type"], cancelled["stop_price"], cancelled["why"]) == ("STP", 102.0, "stopped")
    assert broker._books[TICKER].is_empty


async def test_broker_rejection_alerts(isolated):
    runner, broker, sink = await _runner(isolated, "rej", order_type="limit", limit_offset_pct=0.01)
    await runner._submit(side="SELL", quantity=10, bar=_bar(0, 100, 100, 100, 100))  # nothing held
    await broker.push_bar(TICKER, _bar(1, 100, 102, 99, 101))
    assert [a.event for a in sink.alerts] == [alerts.ORDER_FAILED]
    assert "rejected" in sink.alerts[0].summary
    assert _row(isolated, "rej")["status"] == "rejected"


async def test_market_bundles_are_unchanged(isolated):
    runner, broker, _ = await _runner(isolated, "mkt")
    await runner._submit(side="BUY", quantity=10, bar=_bar(0, 100, 100, 100, 100))
    assert len(runner.orders) == 0
    row = _row(isolated, "mkt")
    assert (row["status"], row["order_type"]) == ("filled", "market")


def test_sfa_run_refuses_unsupported_live_params(isolated, capsys, monkeypatch):
    base = load_bundle("mean_reversion_rsi_bb")
    bundle = dataclasses.replace(base, live_params={**base.live_params, "trailing_stop_loss": 0.05})
    monkeypatch.setattr(runner_module, "load_bundle", lambda name: bundle)

    with pytest.raises(typer.Exit) as exit_info:
        runner_module.run_paper_cli(name="mean_reversion_rsi_bb", json_output=True)

    assert exit_info.value.exit_code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["error"] == "unsupported_live_params"
    assert list(payload["keys"]) == ["trailing_stop_loss"]
    assert state_store.read_pid("mean_reversion_rsi_bb") is None, "refused before writing a PID file"
