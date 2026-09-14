"""
Webhook alerts for the paper runner (lib/live/alerts.py).

No network: every POST goes to a recording fake.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.live import alerts


def _alert(strategy: str = "mean_reversion_rsi_bb") -> alerts.Alert:
    return alerts.Alert(
        event=alerts.GUARD_TRIGGERED,
        strategy=strategy,
        ticker="SPY",
        summary="daily_loss: Realised PnL -0.03 below limit -0.02",
        details={"guard": "daily_loss"},
    )


class _Recorder:
    def __init__(self, status: int = 200, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.status = status
        self.raises = raises

    def __call__(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.raises:
            raise self.raises

        class _Resp:
            status_code = self.status

        return _Resp()


@pytest.mark.parametrize(
    "url, override, expected",
    [
        ("https://ntfy.sh/my-sfa-topic", None, "text"),
        ("https://hooks.slack.com/services/T/B/X", None, "json"),
        ("https://discord.com/api/webhooks/1/abc", None, "json"),
        ("https://ntfy.sh/my-sfa-topic", "json", "json"),
        ("https://example.com/hook", "TEXT", "text"),
        ("https://example.com/hook", "bogus", "json"),
    ],
)
def test_resolve_format(url, override, expected):
    assert alerts.resolve_format(url, override) == expected


def test_no_webhook_means_log_only(monkeypatch):
    monkeypatch.delenv(alerts.ALERT_WEBHOOK_ENV, raising=False)
    post = _Recorder()
    assert alerts.send_alert(_alert(), post=post) is False
    assert post.calls == []


def test_json_payload_reads_in_slack_and_discord():
    post = _Recorder()
    assert alerts.send_alert(_alert(), url="https://hooks.slack.com/x", fmt="json", post=post) is True
    (url, kwargs), = post.calls
    body = kwargs["json"]
    assert body["text"] == body["content"]
    assert "guard triggered" in body["text"] and "daily_loss" in body["text"]
    assert body["event"] == "guard_triggered"
    assert body["details"] == {"guard": "daily_loss"}
    assert kwargs["timeout"] == alerts.TIMEOUT_SECONDS


def test_text_payload_for_ntfy_survives_non_ascii_names():
    post = _Recorder()
    assert alerts.send_alert(_alert(strategy="média_rsi"), url="https://ntfy.sh/t", post=post) is True
    (_, kwargs), = post.calls
    assert kwargs["data"].decode("utf-8").startswith("sfa média_rsi")
    kwargs["headers"]["Title"].encode("latin-1")  # must not raise
    assert kwargs["headers"]["Priority"] == "high"


def test_delivery_failure_never_raises():
    assert alerts.send_alert(_alert(), url="https://x.test", post=_Recorder(raises=OSError("down"))) is False
    assert alerts.send_alert(_alert(), url="https://x.test", post=_Recorder(status=500)) is False


def test_notify_reads_the_env_var(monkeypatch):
    post = _Recorder()
    monkeypatch.setenv(alerts.ALERT_WEBHOOK_ENV, "https://hooks.example.test/sfa")
    monkeypatch.delenv(alerts.ALERT_FORMAT_ENV, raising=False)
    import requests

    monkeypatch.setattr(requests, "post", post)
    assert asyncio.run(alerts.notify(_alert())) is True
    assert post.calls[0][0] == "https://hooks.example.test/sfa"
