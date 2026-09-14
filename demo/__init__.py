"""Public demo of SearchForAlpha Lab.

Everything the hosted demo needs lives in this package, so the research
workspace itself carries no demo branches:

- ``snapshot``   reads the frozen fixture in ``demo/fixtures/`` (prices, fundamentals)
- ``sealing``    refuses the network and the broker path inside the demo process
- ``sessions``   gives every visitor their own dashboard state
- ``limits``     rate limits and the one-job-at-a-time gate for heavy runs
- ``patches``    swaps the live data seams for the snapshot
- ``guards``     wraps the Dash callbacks that start CPU work
- ``banner``     the demo banner and the header badge
- ``server``     the WSGI entry point (``python -m demo.server``)

``DEMO_MODE`` is the kill switch. Unset or false, ``demo.server`` serves a 404
for every page and never imports the dashboard. See ``docs/DEMO.md``.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def enabled() -> bool:
    """True only when ``DEMO_MODE`` is explicitly switched on."""
    return os.environ.get("DEMO_MODE", "").strip().lower() in _TRUE
