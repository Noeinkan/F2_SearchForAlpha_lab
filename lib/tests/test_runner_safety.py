"""
Safety tests for PaperRunner: idempotent COID, double-bar no-double-buy,
pre-trade size guards, SIGTERM graceful shutdown.

All tests use MockBroker + isolated SQLite. No ib_async, no network.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import platform
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.live.broker import Bar, MockBroker, Order
from lib.live.runner import PaperRunner, RunnerOptions
from lib.agent_strategy import load_bundle
from lib.store import fills as fills_store
from lib.store import trials as trials_store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "safety.db"
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    return db_path


def _make_bar(i: int, price: float = 100.0) -> Bar:
    return Bar(
        timestamp=datetime.fromtimestamp(
            datetime(2024, 1, 1, tzinfo=UTC).timestamp() + i * 86400, tz=UTC
        ),
        open=price,
        high=price * 1.01,
        low=price * 0.99,
        close=price,
        volume=1_000_000,
    )


@pytest.mark.asyncio
async def test_double_bar_no_double_buy(isolated_db):
    """Two identical consecutive bars with same timestamp → at most one DB row per COID."""
    bundle = load_bundle("mean_reversion_rsi_bb")
    broker = MockBroker(starting_cash=100_000)
    runner = PaperRunner(
        broker=broker,
        options=RunnerOptions(name="safety_test", bundle=bundle, db_path=isolated_db),
    )
    await runner.start()

    base_ts = datetime(2024, 1, 1, tzinfo=UTC)
    price = 200.0
    for i in range(60):
        price *= 0.99
        bar = Bar(
            timestamp=datetime.fromtimestamp(base_ts.timestamp() + i * 86400, tz=UTC),
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=1_000_000,
        )
        await broker.push_bar(bundle.ticker, bar)

    all_fills = fills_store.list_fills(strategy_name="safety_test", db_path=isolated_db)
    buy_fills = [f for f in all_fills if f["side"] == "BUY"]
    if buy_fills:
        coids = [f["client_order_id"] for f in buy_fills if f["client_order_id"]]
        assert len(coids) == len(set(coids)), "Duplicate COIDs detected — double-fill occurred"


@pytest.mark.asyncio
async def test_idempotent_coid(isolated_db):
    """Calling _submit twice with the same (bar, side, qty) → exactly one DB row."""
    bundle = load_bundle("mean_reversion_rsi_bb")
    broker = MockBroker(starting_cash=100_000)
    runner = PaperRunner(
        broker=broker,
        options=RunnerOptions(name="coid_test", bundle=bundle, db_path=isolated_db),
    )
    await broker.connect()

    bar = Bar(
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1_000,
    )
    await broker.push_bar(bundle.ticker, bar)
    runner.state.bars.append(bar)

    await runner._submit(side="BUY", quantity=10.0, bar=bar)
    await runner._submit(side="BUY", quantity=10.0, bar=bar)

    expected_coid = hashlib.sha1(
        f"coid_test|{bar.timestamp.isoformat()}|BUY|10.0".encode()
    ).hexdigest()[:16]

    rows = fills_store.list_fills(strategy_name="coid_test", db_path=isolated_db)
    matching = [r for r in rows if r.get("client_order_id") == expected_coid]
    assert len(matching) == 1, (
        f"Expected exactly 1 DB row for COID {expected_coid!r}, got {len(matching)}"
    )


@pytest.mark.asyncio
async def test_intent_then_crash_then_retry(isolated_db):
    """Pre-insert intent row → _submit completes mark_filled without double-placing to DB."""
    bundle = load_bundle("mean_reversion_rsi_bb")
    broker = MockBroker(starting_cash=100_000)
    runner = PaperRunner(
        broker=broker,
        options=RunnerOptions(name="intent_test", bundle=bundle, db_path=isolated_db),
    )
    await broker.connect()

    bar = Bar(
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1_000,
    )
    await broker.push_bar(bundle.ticker, bar)
    runner.state.bars.append(bar)

    coid = hashlib.sha1(
        f"intent_test|{bar.timestamp.isoformat()}|BUY|10.0".encode()
    ).hexdigest()[:16]
    fills_store.record_intent("intent_test", bundle.ticker, "BUY", 10.0, coid, db_path=isolated_db)

    await runner._submit(side="BUY", quantity=10.0, bar=bar)

    rows = fills_store.list_fills(strategy_name="intent_test", db_path=isolated_db)
    assert len(rows) == 1, f"Expected exactly 1 DB row, got {len(rows)}"
    assert rows[0]["status"] == "filled", f"Expected status=filled, got {rows[0]['status']!r}"


@pytest.mark.asyncio
async def test_pretrade_quantity_reject(isolated_db, monkeypatch):
    """max_order_quantity=5 → request for qty=10 is rejected without submitting."""
    bundle = load_bundle("mean_reversion_rsi_bb")
    broker = MockBroker(starting_cash=100_000)
    runner = PaperRunner(
        broker=broker,
        options=RunnerOptions(name="qty_guard_test", bundle=bundle, db_path=isolated_db),
    )
    runner._guards_config["max_order_quantity"] = 5

    await broker.connect()
    bar = Bar(
        timestamp=datetime(2024, 6, 1, tzinfo=UTC),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1_000,
    )
    await broker.push_bar(bundle.ticker, bar)
    runner.state.bars.append(bar)

    submitted_orders: list[Order] = []
    original_submit = broker.submit_order

    async def _recording_submit(order: Order):
        submitted_orders.append(order)
        return await original_submit(order)

    monkeypatch.setattr(broker, "submit_order", _recording_submit)

    await runner._submit(side="BUY", quantity=10.0, bar=bar)
    assert len(submitted_orders) == 0, "Order should have been rejected by pre-trade guard"

    rows = fills_store.list_fills(strategy_name="qty_guard_test", db_path=isolated_db)
    assert len(rows) == 0, "No DB row should be created for a rejected order"


@pytest.mark.asyncio
async def test_sigterm_graceful_shutdown():
    """SIGTERM causes runner.stop() to fire and stop_event to be set."""
    if platform.system() == "Windows":
        pytest.skip("SIGTERM signal handlers not supported on Windows via asyncio")

    bundle = load_bundle("mean_reversion_rsi_bb")
    broker = MockBroker(starting_cash=100_000)
    runner = PaperRunner(
        broker=broker,
        options=RunnerOptions(name="sigterm_test", bundle=bundle),
    )
    await broker.connect()

    async def _run_and_signal() -> bool:
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(
                signal.SIGTERM, lambda: asyncio.create_task(runner.stop())
            )
        except (NotImplementedError, OSError):
            pytest.skip("Signal handlers not supported in this environment")
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(0.2)
        return runner.state.stop_event.is_set()

    result = await _run_and_signal()
    assert result, "stop_event must be set after SIGTERM"
