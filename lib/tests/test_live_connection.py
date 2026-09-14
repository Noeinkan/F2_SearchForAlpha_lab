"""
Reconnect backoff and the IB Gateway daily restart window (lib/live/connection.py),
plus the stop-request files sfa kill and the runner exchange (lib/live/stop_request.py).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.live import stop_request
from lib.live.connection import ReconnectPolicy, RestartWindow


def test_backoff_doubles_then_caps():
    policy = ReconnectPolicy(initial_delay_seconds=2, max_delay_seconds=30)
    assert [policy.delay(n) for n in range(6)] == [2, 4, 8, 16, 30, 30]


def test_backoff_from_config_defaults():
    assert ReconnectPolicy.from_config(None) == ReconnectPolicy()
    assert ReconnectPolicy.from_config({"max_delay_seconds": 10}).delay(5) == 10


def test_window_spans_midnight():
    window = RestartWindow(start=time(23, 50), minutes=15, tz=UTC)
    day = datetime(2026, 9, 14, tzinfo=UTC)
    assert not window.contains(day.replace(hour=23, minute=49))
    assert window.contains(day.replace(hour=23, minute=55))
    assert window.contains(day + timedelta(days=1, minutes=4))
    assert not window.contains(day + timedelta(days=1, minutes=6))


def test_window_compares_in_its_own_zone():
    # 23:45 in New York is 03:45 UTC the next day (EDT, UTC-4).
    window = RestartWindow(start=time(23, 45), minutes=15, tz=ZoneInfo("America/New_York"))
    assert window.contains(datetime(2026, 9, 15, 3, 50, tzinfo=UTC))
    assert not window.contains(datetime(2026, 9, 14, 23, 50, tzinfo=UTC))


def test_window_defaults_to_local_time():
    local_now = datetime.now().astimezone()
    start = (local_now - timedelta(minutes=1)).time().replace(second=0, microsecond=0)
    window = RestartWindow(start=start, minutes=10)
    assert window.contains(local_now.astimezone(UTC))


def test_window_from_config():
    assert RestartWindow.from_config(None) is None
    assert RestartWindow.from_config({"window_minutes": 10}) is None
    window = RestartWindow.from_config({"time": "23:45", "window_minutes": 20, "timezone": "Europe/Rome"})
    assert window == RestartWindow(start=time(23, 45), minutes=20, tz=ZoneInfo("Europe/Rome"))


def test_stop_request_round_trip(tmp_path):
    assert stop_request.read_stop_request("s", pid_dir=tmp_path) is None
    stop_request.write_stop_result("s", {"stale": True}, pid_dir=tmp_path)
    stop_request.request_stop("s", flatten=True, pid_dir=tmp_path)
    # a new request clears an outcome left over from an earlier stop
    assert stop_request.pop_stop_result("s", pid_dir=tmp_path) is None
    assert stop_request.read_stop_request("s", pid_dir=tmp_path) == {"flatten": True}
    assert stop_request.stop_request_pending("s", pid_dir=tmp_path)
    stop_request.clear_stop_request("s", pid_dir=tmp_path)
    assert not stop_request.stop_request_pending("s", pid_dir=tmp_path)
    stop_request.write_stop_result("s", {"flatten": {"flattened": True}}, pid_dir=tmp_path)
    assert stop_request.pop_stop_result("s", pid_dir=tmp_path) == {"flatten": {"flattened": True}}
    assert stop_request.pop_stop_result("s", pid_dir=tmp_path) is None
    assert list(tmp_path.iterdir()) == []
