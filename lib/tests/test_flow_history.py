"""Historical option chain and replay (ThetaData EOD), with the terminal faked."""

from __future__ import annotations

from datetime import date

import pytest
import requests

from lib.dash import flow_history, flow_paper, flow_store
from lib.dash.flow_chain import table_from_report
from lib.options import theta_history

TODAY = date(2026, 11, 15)
ENTRY = date(2026, 3, 2)          # a Monday inside the one-year window
EXPIRY = "2026-03-06"
HEADER = "symbol,expiration,strike,right,created,last_trade,open,high,low,close,volume,count,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition"


def _csv(*rows: str) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def _row(day: str, strike: str, right: str, bid: str, ask: str, expiry: str = "2026-03-06") -> str:
    return f"TSLA,{expiry},{strike},{right},{day}T17:15:00.000,{day}T15:59:00.000,1,1,1,1,10,1,1,1,{bid},0,1,1,{ask},0"


class _Response:
    def __init__(self, status: int, text: str):
        self.status_code, self.text = status, text


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    monkeypatch.setattr(flow_history, "HISTORY_DIR", tmp_path / "flow-history")
    return tmp_path


def test_eod_rows_parse_to_quotes_with_report_time_in_utc():
    def fake_get(url, params, timeout):
        assert url.endswith("/option/history/eod")
        assert params["expiration"] == "*" and params["start_date"] == "20260302" and params["format"] == "csv"
        return _Response(200, _csv(_row("2026-03-02", "400.000", "CALL", "10.10", "10.30"),
                                   _row("2026-03-02", "390.000", "PUT", "0", "4.20")))

    quotes = theta_history.option_eod("tsla", ENTRY, ENTRY, session_get=fake_get)
    call, put = quotes
    assert (call["cp"], call["strike"], call["bid"], call["ask"], call["expiry"]) == ("C", 400.0, 10.10, 10.30, EXPIRY)
    # 17:15 New York in March (EST, UTC-5) is 22:15 UTC.
    assert call["observed_at"] == "2026-03-02T22:15:00+00:00" and call["date"] == "2026-03-02"
    assert put["bid"] is None and put["ask"] == 4.20  # a zero bid is "no quote", never $0


def test_terminal_not_running_is_a_clear_error():
    def refused(*_args, **_kwargs):
        raise requests.ConnectionError("refused")

    with pytest.raises(theta_history.ThetaUnavailable, match="Theta Terminal is not running"):
        theta_history.option_eod("TSLA", ENTRY, ENTRY, session_get=refused)


def test_no_data_answer_is_an_empty_table():
    assert theta_history.option_eod("TSLA", ENTRY, ENTRY, session_get=lambda *a, **k: _Response(472, "No data")) == []


def test_trade_date_must_sit_inside_the_plan_window():
    with pytest.raises(ValueError, match="one day delayed"):
        flow_history.check_trade_date(TODAY, today=TODAY)
    with pytest.raises(ValueError, match="365 days"):
        flow_history.check_trade_date(date(2025, 1, 6), today=TODAY)
    with pytest.raises(ValueError, match="weekend"):
        flow_history.check_trade_date(date(2026, 3, 1), today=TODAY)


def _fake_theta(monkeypatch, *, leg_days, closes):
    def option_eod(symbol, start, end, *, expiration="*", strike=None, right="both", session_get=None):
        if expiration == "*":
            return [
                {"date": "2026-03-02", "observed_at": "2026-03-02T22:15:00+00:00", "expiry": EXPIRY, "cp": "C",
                 "strike": 400.0, "bid": 10.0, "ask": 10.2, "close": 10.1, "volume": 50.0, "multiplier": 100},
                {"date": "2026-03-02", "observed_at": "2026-03-02T22:15:00+00:00", "expiry": "2026-01-16", "cp": "P",
                 "strike": 300.0, "bid": None, "ask": None, "close": None, "volume": 0.0, "multiplier": 100},
                {"date": "2026-03-02", "observed_at": "2026-03-02T22:15:00+00:00", "expiry": EXPIRY, "cp": "P",
                 "strike": 380.0, "bid": None, "ask": 1.5, "close": None, "volume": 0.0, "multiplier": 100},
            ]
        assert (expiration, strike, right) == (EXPIRY, 400.0, "C")
        return [{"date": d, "observed_at": f"{d}T22:15:00+00:00", "expiry": EXPIRY, "cp": "C", "strike": 400.0,
                 "bid": bid, "ask": ask, "close": None, "volume": 1.0, "multiplier": 100}
                for d, (bid, ask) in leg_days.items()]

    monkeypatch.setattr(theta_history, "option_eod", option_eod)
    monkeypatch.setattr(theta_history, "stock_eod", lambda symbol, start, end, session_get=None: {
        d: c for d, c in closes.items() if start.isoformat() <= d <= end.isoformat()})


def test_historical_chain_lists_contracts_quoted_that_day_including_expired(isolated, monkeypatch):
    _fake_theta(monkeypatch, leg_days={}, closes={"2026-03-02": 395.0})
    record = flow_history.load_chain("tsla", "2026-03-02", today=TODAY)
    assert record["underlying"] == 395.0 and record["observed_at"] == "2026-03-02T22:15:00+00:00"
    report = flow_history.chain_report(record)
    assert set(report["option_chains"]) == {"2026-01-16", EXPIRY}
    # Cached: a second load does not call the terminal.
    monkeypatch.setattr(theta_history, "option_eod", lambda *a, **k: pytest.fail("refetched"))
    assert flow_history.load_chain("TSLA", "2026-03-02", today=TODAY)["contracts"] == record["contracts"]

    children = table_from_report(report, expiry=EXPIRY, theme={}, view="all")
    text = str(children)
    assert "Historical end-of-day quotes" in text and "data-observed" in text
    assert "No bid in the end-of-day report" in text  # the 380 put has an ask but no bid


def test_replay_runs_to_expiry_and_flags_missing_quotes(isolated, monkeypatch):
    days = {"2026-03-02": (10.0, 10.2), "2026-03-04": (12.0, 12.3), "2026-03-05": (None, 9.0), "2026-03-06": (15.0, 15.2)}
    closes = {d: 400.0 for d in ("2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06")}
    _fake_theta(monkeypatch, leg_days=days, closes=closes)
    replay = flow_history.build_replay("TSLA", "2026-03-02", [{"key": f"{EXPIRY}|C|400", "side": "buy", "qty": 1}],
                                       nonce=7, today=TODAY)
    assert [s["date"] for s in replay["snapshots"]] == sorted(closes)
    assert replay["ended_early"] is False and replay["last_available"] == EXPIRY
    by_day = {s["date"]: s for s in replay["snapshots"]}
    assert by_day["2026-03-03"]["missing"] == [{"key": f"{EXPIRY}|C|400", "what": "no quote"}]
    assert by_day["2026-03-05"]["missing"] == [{"key": f"{EXPIRY}|C|400", "what": "no bid"}]
    assert flow_history.find_replay_by_nonce("TSLA", 7)["id"] == replay["id"]

    # The paper simulator runs on the replay unchanged: buy at the entry ask, close at a later bid.
    timeline = flow_paper.timeline("TSLA", replay["id"])
    p = flow_paper.buy("TSLA", timeline[0], f"{EXPIRY}|C|400", fee=0, replay=replay["id"])
    assert p["entry_ask"] == 10.2 and p["replay"] == replay["id"]
    closed = flow_paper.close("TSLA", p["id"], timeline[2], fee=0)
    assert closed["pnl"] == pytest.approx((12.0 - 10.2) * 100)
    # Trades made in a replay stay out of the recorded-scan view.
    assert not flow_paper.in_context(closed, None) and flow_paper.in_context(closed, replay["id"])


def test_replay_stops_at_last_available_day_when_history_ends_before_expiry(isolated, monkeypatch):
    days = {"2026-03-02": (10.0, 10.2), "2026-03-03": (11.0, 11.2)}
    _fake_theta(monkeypatch, leg_days=days, closes={"2026-03-02": 400.0, "2026-03-03": 401.0})
    replay = flow_history.build_replay("TSLA", "2026-03-02", [{"key": f"{EXPIRY}|C|400", "side": "buy", "qty": 1}],
                                       today=date(2026, 3, 4))
    assert replay["ended_early"] is True and replay["last_available"] == "2026-03-03"
    assert replay["snapshots"][-1]["date"] == "2026-03-03"


def test_replay_refuses_mixed_expiries(isolated):
    with pytest.raises(ValueError, match="same expiry"):
        flow_history.build_replay("TSLA", "2026-03-02", [
            {"key": f"{EXPIRY}|C|400", "side": "buy", "qty": 1},
            {"key": "2026-03-13|C|410", "side": "sell", "qty": 1}], today=TODAY)
