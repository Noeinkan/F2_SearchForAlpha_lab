"""Transient-vs-permanent classification on the market-data fetch path.

Before this, a Yahoo 429 and an unknown ticker were indistinguishable by the
time they reached the dashboard: both arrived as a stringified DataFetchError.
Nothing in the suite simulated an HTTP failure at all.
"""

import pandas as pd
import pytest

from lib.fetch_errors import (
    DataFetchError,
    TransientFetchError,
    classify_fetch_error,
    retry_with_backoff,
)


class _Response:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _HttpError(Exception):
    def __init__(self, message, status_code, headers=None):
        super().__init__(message)
        self.response = _Response(status_code, headers)


# --- classification ---------------------------------------------------------

@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_statuses_classify_as_transient(status):
    err = classify_fetch_error(_HttpError("boom", status), "failed")
    assert isinstance(err, TransientFetchError)
    assert err.status_code == status


@pytest.mark.parametrize("status", [400, 403, 404])
def test_permanent_statuses_stay_permanent(status):
    err = classify_fetch_error(_HttpError("nope", status), "failed")
    assert isinstance(err, DataFetchError)
    assert not isinstance(err, TransientFetchError)


def test_retry_after_header_is_parsed():
    err = classify_fetch_error(
        _HttpError("slow down", 429, {"Retry-After": "7"}), "failed"
    )
    assert err.retry_after == 7.0


def test_rate_limit_detected_without_a_status_code():
    """curl_cffi surfaces errors as bare strings with no response attribute."""
    err = classify_fetch_error(Exception("Too Many Requests"), "failed")
    assert isinstance(err, TransientFetchError)
    assert err.status_code is None


def test_timeouts_are_transient():
    assert isinstance(classify_fetch_error(TimeoutError(), "failed"), TransientFetchError)
    assert isinstance(
        classify_fetch_error(ConnectionError(), "failed"), TransientFetchError
    )


def test_unknown_ticker_is_not_retryable():
    err = classify_fetch_error(ValueError("No data found, symbol may be delisted"), "x")
    assert not isinstance(err, TransientFetchError)


# --- retry policy -----------------------------------------------------------

def test_transient_errors_are_retried_up_to_the_cap():
    calls, slept = [], []

    def op():
        calls.append(1)
        raise TransientFetchError("429")

    with pytest.raises(TransientFetchError):
        retry_with_backoff(op, describe="test", sleep=slept.append)

    assert len(calls) == 3, "one initial attempt plus two retries"
    assert slept == [1.0, 2.0], "exponential backoff"


def test_permanent_errors_are_not_retried():
    calls = []

    def op():
        calls.append(1)
        raise DataFetchError("delisted")

    with pytest.raises(DataFetchError):
        retry_with_backoff(op, describe="test", sleep=lambda _: None)

    assert len(calls) == 1


def test_retry_succeeds_after_a_transient_blip():
    state = {"n": 0}

    def op():
        state["n"] += 1
        if state["n"] == 1:
            raise TransientFetchError("503")
        return "ok"

    assert retry_with_backoff(op, describe="test", sleep=lambda _: None) == "ok"
    assert state["n"] == 2


def test_retry_after_raises_the_wait_but_is_capped():
    slept = []

    def op():
        raise TransientFetchError("429", retry_after=9999.0)

    with pytest.raises(TransientFetchError):
        retry_with_backoff(op, describe="test", sleep=slept.append)

    assert all(w <= 8.0 for w in slept), "must not hang a Dash callback"


# --- end to end through fetch_data -----------------------------------------

def test_fetch_data_surfaces_a_429_as_transient(monkeypatch):
    import lib.data_processing as dp

    def boom(*_args, **_kwargs):
        raise _HttpError("Too Many Requests", 429)

    monkeypatch.setattr(dp.yf, "Ticker", lambda *_a, **_k: type("T", (), {"history": boom})())

    with pytest.raises(TransientFetchError) as excinfo:
        dp.fetch_data("AAPL", "2024-01-01", "2024-02-01", validate=False)
    assert excinfo.value.status_code == 429


def test_fetch_data_empty_frame_is_not_transient(monkeypatch):
    """An empty result means 'no such data', which retrying cannot fix."""
    import lib.data_processing as dp

    monkeypatch.setattr(
        dp.yf,
        "Ticker",
        lambda *_a, **_k: type("T", (), {"history": lambda *a, **k: pd.DataFrame()})(),
    )

    with pytest.raises(DataFetchError) as excinfo:
        dp.fetch_data("NOPE", "2024-01-01", "2024-02-01", validate=False)
    assert not isinstance(excinfo.value, TransientFetchError)
