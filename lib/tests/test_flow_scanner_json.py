"""Tests for Flow Scanner JSON export."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

from scripts.flow_scanner import (
    Contract,
    TickerReport,
    UnusualFlag,
    main,
    reports_to_json,
    write_json_report,
)


def _sample_report() -> TickerReport:
    expiry = date(2026, 6, 20)
    contract = Contract(
        ticker="NVDA",
        expiry=expiry,
        strike=210.0,
        cp="C",
        last=4.10,
        bid=4.05,
        ask=4.15,
        volume=55471,
        open_interest=5000,
        iv=0.315,
    )
    flag = UnusualFlag(kind="unusual", contract=contract, message="C 210 vol>5000")
    report = TickerReport(
        ticker="NVDA",
        spot=205.19,
        prev_close=204.87,
        day_low=203.44,
        day_high=207.07,
        wk52_low=142.03,
        wk52_high=236.54,
        contracts=[contract],
        flags=[flag],
        pc_vol_ratio=0.7,
        call_pct=58.8,
        put_pct=41.2,
        unusual_score=2,
        top_call_strikes=[(210.0, 55471)],
        top_put_strikes=[(200.0, 12000)],
    )
    return report


def test_reports_to_json_includes_contracts_and_flags():
    payload = json.loads(reports_to_json([_sample_report()], today=date(2026, 6, 14)))
    assert "reports" in payload
    report = payload["reports"][0]
    assert report["ticker"] == "NVDA"
    assert report["contracts"]
    row = report["contracts"][0]
    assert row["expiry"] == "2026-06-20"
    assert row["is_otm"] is True
    assert row["flags"][0]["kind"] == "unusual"
    assert report["top_call_strikes"] == [[210.0, 55471]]


def test_write_json_report_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "flow_report.json"
        write_json_report([_sample_report()], str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data["reports"]) == 1


def test_cli_json_out_flag(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        json_path = Path(tmp) / "out.json"
        html_path = Path(tmp) / "out.html"

        def fake_scan(*_args, **_kwargs):
            return [_sample_report()]

        monkeypatch.setattr("scripts.flow_scanner.scan_tickers", fake_scan)
        rc = main(["NVDA", "--no-html", "--json-out", str(json_path), "--output", str(html_path), "--quiet"])
        assert rc == 0
        assert json_path.is_file()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["reports"][0]["ticker"] == "NVDA"
