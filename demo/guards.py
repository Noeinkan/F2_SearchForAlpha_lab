"""Server-side guards around the callbacks that start CPU work.

Dash keeps every registered callback in ``app.callback_map`` as a function of
the flat input and state values. ``install`` wraps the handful that matter
without touching the modules that define them:

- **Size caps** rewrite an argument before the original sees it (combinations,
  signals per side, grid size, Bayesian trials). The inputs also carry the cap
  as their ``max`` (``demo.banner``), so a visitor rarely meets the clamp.
- **Rate limits** count backtests, data loads and fundamentals loads per IP
  per minute, and optimiser runs per IP per hour.
- **The job gate** admits at most ``max_concurrent_jobs`` optimiser runs across
  all visitors. Grid search, the Bayesian sweep and walk-forward validation are
  process-wide singletons in the dashboard; in the demo only the visitor who
  started one may poll or stop it, instead of the next visitor's click
  cancelling it.
- **The Flow Scanner** is answered with a notice: it needs a live options chain.
- **Usage and the daily cap per person** go through ``access`` (a
  ``demo.access.gate.AccessGate``, or None with the gate off): every backtest,
  data load, fundamentals load, optimiser run and refusal is recorded against
  the signed-in email, and an optimiser run past that email's daily cap is
  refused like any other limit.

A refused request never raises into the browser. It returns a normal callback
response that changes nothing except ``demo-wall``, a notice saying what ran
out, when it resets and what to do instead.
"""

from __future__ import annotations

import json
import logging
import threading
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from dash._utils import to_json
from dash.exceptions import PreventUpdate
from flask import request

from demo import sessions
from demo.limits import JobGate, SlidingWindowLimiter
from demo.patches import FLOW_OFF_MESSAGE
from demo.settings import DemoSettings

logger = logging.getLogger(__name__)

WALL_ID = "demo-wall"
WALL_BODY_ID = "demo-wall-body"


# --------------------------------------------------------------------------- helpers


def client_ip() -> str:
    # nginx is the only thing that can reach the container and it sets X-Real-IP.
    return (request.headers.get("X-Real-IP") or request.remote_addr or "unknown").strip()


def _dep_names(deps: list[dict[str, Any]]) -> list[str]:
    names = []
    for dep in deps:
        dep_id = dep.get("id")
        names.append(f"{dep_id}.{dep.get('property')}" if isinstance(dep_id, str) else "")
    return names


def wall_response(message: str, *, tone: str = "warn") -> str:
    """A callback response that only opens the demo notice."""
    return to_json(
        {
            "multi": True,
            "response": {},
            "sideUpdate": {
                WALL_ID: {"hidden": False, "className": f"sfa-demo-wall sfa-demo-wall--{tone}"},
                WALL_BODY_ID: {"children": message},
            },
        }
    )


def _with_notice(raw: Any, message: str) -> Any:
    """Add the demo notice to a response the original callback produced."""
    if not isinstance(raw, str):
        return raw
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw
    side = payload.setdefault("sideUpdate", {})
    side[WALL_ID] = {"hidden": False, "className": "sfa-demo-wall sfa-demo-wall--info"}
    side[WALL_BODY_ID] = {"children": message}
    return json.dumps(payload)


def _seconds(value: float) -> str:
    value = max(1, int(round(value)))
    return f"{value} s" if value < 90 else f"{max(1, round(value / 60))} min"


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- guards


class DemoGuards:
    def __init__(self, app, store: sessions.SessionStore, settings: DemoSettings, access=None) -> None:
        self.app = app
        self.store = store
        self.settings = settings
        self.access = access
        self.gate = JobGate(settings.max_concurrent_jobs, settings.job_timeout_seconds)
        self.actions = SlidingWindowLimiter(settings.actions_per_ip_per_minute, 60)
        self.jobs = SlidingWindowLimiter(settings.jobs_per_ip_per_hour, 3600)
        self._last_owner: dict[str, str] = {}
        # Progress is polled by dcc.Interval. When a poll outlasts the interval,
        # the renderer fires the next one and *drops the reply to the one in
        # flight* -- so the reply carrying "completed" can be thrown away, and
        # every later poll finds a finished run and changes nothing: the page
        # sits at "Testing 95/100" for good. Polls are therefore serialised per
        # visitor, and the final reply is kept so a later poll can replay it.
        self._final_replies: dict[tuple[str, str], str] = {}
        self._poll_locks: dict[str, threading.Lock] = {}
        self._poll_locks_guard = threading.Lock()
        self.clamps: dict[str, int] = {
            "max-combos-input.value": settings.max_combos,
            "max-signals-slider.value": settings.max_signals_per_side,
            "grid-max-combos-input.value": settings.max_grid_combos,
            "bayesian-trials-input.value": settings.max_bayes_trials,
        }
        self.wrapped: dict[str, list[str]] = {}

    # ----------------------------------------------------------------- install

    def install(self) -> None:
        for key, entry in list(self.app.callback_map.items()):
            if "callback" not in entry:
                continue  # clientside callbacks run in the browser
            inputs = _dep_names(entry.get("inputs", []))
            states = _dep_names(entry.get("state", []))
            names = inputs + states
            outputs = key
            layers: list[str] = []
            func = entry["callback"]

            if any(name in self.clamps for name in names):
                func = self._clamping(func, names)
                layers.append("clamp")

            if "backtest-results.children" in outputs and "run-backtest-btn.n_clicks" in inputs:
                func = self._rate_limited(func, "backtests", "backtest")
                layers.append("actions")
            elif "data-loaded-store.data" in outputs and "load-data-button.n_clicks" in inputs:
                func = self._rate_limited(func, "data loads", "data_load")
                layers.append("actions")
            elif "fundamentals-store.data" in outputs:
                func = self._rate_limited(func, "fundamentals loads", "fundamentals_load")
                layers.append("actions")

            if "run-optimization-btn.n_clicks" in inputs and "optimization-state.data" in outputs:
                func = self._combos_start(func, names)
                layers.append("combos-start")
            elif "optimization-interval.n_intervals" in inputs:
                func = self._combos_tick(func)
                layers.append("combos-tick")

            for kind, start_input, poll_input in (
                ("grid", "run-grid-btn.n_clicks", "grid-interval.n_intervals"),
                ("bayesian", "run-bayesian-btn.n_clicks", "bayesian-interval.n_intervals"),
                ("walk-forward", "validate-oos-btn.n_clicks", "optimizer-oos-interval.n_intervals"),
            ):
                if start_input in inputs:
                    func = self._singleton_start(func, kind)
                    layers.append(f"{kind}-start")
                elif poll_input in inputs:
                    func = self._singleton_poll(func, kind)
                    layers.append(f"{kind}-poll")

            if "flow-content.children" in outputs and "flow-rescan-button.n_clicks" in inputs:
                func = self._flow_off(func, inputs)
                layers.append("flow-off")

            if layers:
                entry["callback"] = func
                self.wrapped[key] = layers
        logger.info("demo guards wrapped %d callbacks", len(self.wrapped))

    # ----------------------------------------------------------------- layers

    def _clamping(self, func: Callable, names: list[str]) -> Callable:
        positions = [(i, self.clamps[n]) for i, n in enumerate(names) if n in self.clamps]

        def clamped(*args: Any, **kwargs: Any):
            args = list(args)
            for index, cap in positions:
                if index < len(args):
                    value = _as_int(args[index])
                    if value is None or value > cap:
                        args[index] = cap
            return func(*args, **kwargs)

        return clamped

    def _track(self, kind: str, detail: str | None = None) -> None:
        if self.access is not None:
            self.access.record(kind, detail)

    def _ticker(self) -> str | None:
        sid = sessions.current_sid.get()
        state = self.store.peek(sid) if sid else None
        return getattr(state, "ticker", None)

    def _rate_limited(self, func: Callable, label: str, kind: str) -> Callable:
        limit = self.settings.actions_per_ip_per_minute

        def limited(*args: Any, **kwargs: Any):
            wait = self.actions.hit(client_ip())
            if wait:
                self._track("limit", f"{label} per minute")
                return wall_response(
                    f"That is {limit} {label} and other runs in the last minute from your connection, "
                    f"the most this public demo allows. The next one is available in {_seconds(wait)}."
                )
            raw = func(*args, **kwargs)
            self._track(kind, self._ticker())
            return raw

        return limited

    def _refuse_job(self, kind: str) -> str | None:
        """Common admission checks for any optimiser run. None means go."""
        owner = sessions.current_sid.get() or ""
        refusal = None
        if not self.gate.admit(kind, owner):
            refusal = (
                f"{self.settings.max_concurrent_jobs} optimiser runs are already going on this demo, "
                "shared by everyone visiting it. Try again in a minute; backtests still run meanwhile."
            )
        elif self.access is not None and (daily := self.access.refuse_job()):
            refusal = daily
        elif wait := self.jobs.hit(client_ip()):
            refusal = (
                f"This demo allows {self.settings.jobs_per_ip_per_hour} optimiser runs an hour per visitor. "
                f"The next one is available in {_seconds(wait)}."
            )
        if refusal:
            self._track("limit", f"{kind}: {refusal[:80]}")
        return refusal

    @contextmanager
    def _serialised(self, key: str) -> Iterator[None]:
        with self._poll_locks_guard:
            lock = self._poll_locks.setdefault(key, threading.Lock())
        if not lock.acquire(timeout=60):
            raise PreventUpdate  # the poll ahead of this one is still working; the next tick retries
        try:
            yield
        finally:
            lock.release()

    def prune(self) -> None:
        """Forget replies and locks of visitors whose state has expired."""
        for key in list(self._final_replies):
            if self.store.peek(key[1]) is None:
                self._final_replies.pop(key, None)
        with self._poll_locks_guard:
            for key in list(self._poll_locks):
                sid = key.split(":", 1)[-1]
                if self.store.peek(sid) is None and not self._poll_locks[key].locked():
                    del self._poll_locks[key]

    def _combos_start(self, func: Callable, names: list[str]) -> Callable:
        label_index = names.index("run-optimization-btn.children") if "run-optimization-btn.children" in names else None

        def start(*args: Any, **kwargs: Any):
            sid = sessions.current_sid.get() or ""
            state = self.store.get(sid)
            self._final_replies.pop(("combos", sid), None)  # a new run or a stop: the old reply is void
            label = str(args[label_index] if label_index is not None and label_index < len(args) else "").upper()
            if "STOP" in label or state.optimization_state.get("running"):
                return func(*args, **kwargs)  # a stop, or a double click the original ignores

            refusal = self._refuse_job("combos")
            if refusal:
                return wall_response(refusal)

            raw = func(*args, **kwargs)
            if state.optimization_state.get("running"):
                self.gate.register(
                    "combos",
                    sid,
                    probe=lambda: bool((self.store.peek(sid) or state).optimization_state.get("running")),
                    cancel=lambda reason: self._stop_combos(state, reason),
                    polled=True,
                )
                self._track("optimizer", f"combos {state.ticker}")
            return raw

        return start

    def _stop_combos(self, state, reason: str) -> None:
        opt = state.optimization_state
        if reason == "timeout":
            # Finish on the next tick with what has already been ranked: the
            # batch callback completes as soon as current_index reaches total.
            done = int(opt.get("current_index") or 0)
            opt["total_combinations"] = min(int(opt.get("total_combinations") or 0), done + 1)
            opt["demo_notice"] = (
                f"Stopped at this demo's {self.settings.job_timeout_seconds} s limit per run; "
                "the leaderboard ranks the combinations that finished."
            )
        else:
            state.reset_optimization()

    def _combos_tick(self, func: Callable) -> Callable:
        def tick(*args: Any, **kwargs: Any):
            sid = sessions.current_sid.get() or ""
            with self._serialised(f"combos:{sid}"):
                self.gate.touch("combos", sid)
                self.gate.sweep()
                state = self.store.get(sid)
                if not state.optimization_state.get("running"):
                    replay = self._final_replies.get(("combos", sid))
                    if replay is not None:
                        return replay
                notice = state.optimization_state.get("demo_notice")
                raw = func(*args, **kwargs)
                if not state.optimization_state.get("running"):
                    if notice:
                        state.optimization_state.pop("demo_notice", None)
                        raw = _with_notice(raw, notice)
                    self._final_replies[("combos", sid)] = raw
                return raw

        return tick

    def _singleton(self, kind: str) -> tuple[dict, Any]:
        if kind == "grid":
            from lib.dash.callbacks import optimizer_grid as module

            return module._grid_job, module._grid_cancel
        from lib.dash.callbacks import optimizer_phase3 as module

        if kind == "bayesian":
            return module._bayesian_job, module._bayesian_cancel
        return module._oos_job, module._oos_cancel

    def _singleton_start(self, func: Callable, kind: str) -> Callable:
        def start(*args: Any, **kwargs: Any):
            sid = sessions.current_sid.get() or ""
            job, cancel_event = self._singleton(kind)
            if job.get("running"):
                if self._last_owner.get(kind) == sid:
                    return func(*args, **kwargs)  # the owner pressing STOP
                return wall_response(
                    f"Another visitor's {kind.replace('-', ' ')} run is in progress. This demo runs one at a "
                    "time; try again in a minute."
                )

            refusal = self._refuse_job(kind)
            if refusal:
                return wall_response(refusal)

            self._final_replies.pop((kind, sid), None)
            raw = func(*args, **kwargs)
            if job.get("running"):
                self._last_owner[kind] = sid

                def cancel(reason: str, job=job, cancel_event=cancel_event) -> None:
                    cancel_event.set()
                    job["cancelled"] = True

                self.gate.register(kind, sid, probe=lambda job=job: bool(job.get("running")), cancel=cancel)
                self._track("optimizer", f"{kind} {self._ticker() or ''}".strip())
            return raw

        return start

    def _singleton_poll(self, func: Callable, kind: str) -> Callable:
        def poll(*args: Any, **kwargs: Any):
            sid = sessions.current_sid.get() or ""
            owner = self._last_owner.get(kind)
            if owner and owner != sid:
                raise PreventUpdate  # not yours to read, or to consume
            job, _ = self._singleton(kind)
            with self._serialised(f"{kind}:{sid}"):
                self.gate.sweep()
                try:
                    raw = func(*args, **kwargs)
                except PreventUpdate:
                    # The original found nothing new. If the result was already
                    # handed out in a reply the renderer dropped, hand it out again.
                    replay = self._final_replies.get((kind, sid))
                    if replay is not None and not job.get("running"):
                        return replay
                    raise
                if not job.get("running") and job.get("result") is None and job.get("error") is None:
                    # This reply consumed the result: it is the final one.
                    self._final_replies[(kind, sid)] = raw
                    self._last_owner.pop(kind, None)
                return raw

        return poll

    def _flow_off(self, func: Callable, inputs: list[str]) -> Callable:
        path_index = inputs.index("app-url.pathname") if "app-url.pathname" in inputs else None

        def flow(*args: Any, **kwargs: Any):
            from lib.dash.dash_config import get_theme
            from lib.dash.flow_view import render_flow_placeholder
            from lib.dash.routes import is_flow_route

            pathname = args[path_index] if path_index is not None else None
            if not is_flow_route(pathname):
                return func(*args, **kwargs)
            placeholder = render_flow_placeholder(get_theme(), FLOW_OFF_MESSAGE)
            return to_json(
                {
                    "multi": True,
                    "response": {
                        "flow-content": {"children": placeholder},
                        "flow-status": {"children": "Off in the demo"},
                        "flow-rescan-button": {"disabled": True},
                    },
                }
            )

        return flow
