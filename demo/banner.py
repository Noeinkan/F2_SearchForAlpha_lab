"""What tells a visitor this is a demo.

Three pieces, all added to the app from outside the layout modules:

1. **Header badge** -- the header's ``CONNECTED`` label becomes
   ``DEMO · DATA 11 SEP 2026`` with an amber dot. It is always on screen, so no
   frame of the demo can be mistaken for a live terminal.
2. **Banner** -- one dismissible line (per browser session) saying what is
   frozen, what is switched off and where the limits are written down, plus
   who is signed in and until when. It is plain HTML in the index page,
   outside React, so it shows before the app has loaded.
3. **Wall** -- the ``demo-wall`` notice ``demo.guards`` opens when a cap or a
   rate limit refuses something.

The inputs that have a demo cap also get it as their ``max``, so the form says
what the server will enforce.
"""

from __future__ import annotations

import html as html_escape
from typing import Any, Iterator

from dash import Input, Output, html

from demo import snapshot
from demo.access.gate import ACCOUNT_MARKER
from demo.guards import WALL_BODY_ID, WALL_ID
from demo.settings import DemoSettings

DOCS_URL = "https://github.com/Noeinkan/F2_SearchForAlpha_lab/blob/main/docs/DEMO.md"

_CSS = """
.sfa-demo-banner{position:fixed;left:50%;bottom:34px;transform:translateX(-50%);z-index:3000;
  display:flex;align-items:center;gap:12px;max-width:min(920px,calc(100vw - 24px));
  padding:8px 10px 8px 14px;background:rgba(17,17,17,.96);color:var(--text-primary,#e8e8e8);
  border:1px solid #2a2a2a;border-left:3px solid var(--warn,#FFCA28);border-radius:4px;
  font:500 12.5px/1.4 var(--font-sans,system-ui,sans-serif);box-shadow:0 6px 24px rgba(0,0,0,.45)}
.sfa-demo-banner strong{color:var(--warn,#FFCA28);font-family:var(--font-mono,monospace);font-weight:600;letter-spacing:.04em}
.sfa-demo-banner a{color:var(--accent,#FFA726);white-space:nowrap}
.sfa-demo-banner button,.sfa-demo-wall button{background:none;border:0;color:var(--text-secondary,#a8a8a8);
  font-size:16px;line-height:1;cursor:pointer;padding:2px 4px}
.sfa-demo-banner[hidden]{display:none}
.sfa-demo-account{display:block;margin-top:3px;color:var(--text-secondary,#a8a8a8)}
.sfa-demo-account b{color:var(--text-primary,#e8e8e8);font-weight:600}
.sfa-demo-account form{display:inline}
.sfa-demo-banner .sfa-demo-signout{font:inherit;color:var(--accent,#FFA726);text-decoration:underline;padding:0}
.sfa-demo-wall{position:fixed;top:54px;left:50%;transform:translateX(-50%);z-index:3100;
  display:flex;align-items:flex-start;gap:10px;max-width:min(640px,calc(100vw - 24px));padding:10px 10px 10px 14px;
  background:#141414;color:var(--text-primary,#e8e8e8);border:1px solid #2a2a2a;border-radius:4px;
  border-left:3px solid var(--warn,#FFCA28);font:500 13px/1.45 var(--font-sans,system-ui,sans-serif);
  box-shadow:0 8px 28px rgba(0,0,0,.5)}
.sfa-demo-wall--info{border-left-color:var(--info,#4FC3F7)}
.sfa-demo-wall[hidden]{display:none}
@media (max-width:700px){.sfa-demo-banner{bottom:30px;font-size:12px}}
"""

_JS = """
(function(){try{if(sessionStorage.getItem('sfaDemoBanner')==='closed'){
  document.documentElement.classList.add('sfa-demo-banner-closed');}}catch(e){}
document.addEventListener('click',function(ev){var b=ev.target.closest&&ev.target.closest('#sfa-demo-banner-close');
  if(!b)return;var el=document.getElementById('sfa-demo-banner');if(el)el.hidden=true;
  try{sessionStorage.setItem('sfaDemoBanner','closed');}catch(e){}});
document.addEventListener('DOMContentLoaded',function(){
  if(document.documentElement.classList.contains('sfa-demo-banner-closed')){
    var el=document.getElementById('sfa-demo-banner');if(el)el.hidden=true;}});
})();
"""


def badge_text() -> str:
    return f"DEMO · DATA {snapshot.snapshot_label().upper()}"


def banner_html(settings: DemoSettings) -> str:
    label = html_escape.escape(snapshot.snapshot_label())
    return (
        f'<style>{_CSS}</style><script>{_JS}</script>'
        '<div id="sfa-demo-banner" class="sfa-demo-banner" role="region" aria-label="About this demo">'
        '<span><strong>PUBLIC DEMO</strong> &nbsp;Prices and fundamentals are frozen at the '
        f'{label} close and never refresh. No broker connection, no orders. '
        f'Optimiser runs are capped (up to {settings.max_combos} combinations a search) so every visitor gets a turn.'
        # demo.access.gate swaps this for "Signed in as … · free trial until …" per request.
        f"{ACCOUNT_MARKER}</span>"
        f'<a href="{DOCS_URL}" target="_blank" rel="noopener noreferrer">What is limited</a>'
        '<button type="button" id="sfa-demo-banner-close" aria-label="Dismiss the demo banner">×</button>'
        "</div>"
    )


def inject_index(index_string: str, settings: DemoSettings) -> str:
    marker = "{%app_entry%}"
    if marker not in index_string:
        raise RuntimeError("index_string has no {%app_entry%} to anchor the demo banner")
    title = "<title>SearchForAlpha - Trading Dashboard</title>"
    index_string = index_string.replace(title, "<title>SearchForAlpha Lab — public demo</title>")
    return index_string.replace(marker, banner_html(settings) + marker, 1)


def _walk(component: Any) -> Iterator[Any]:
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and hasattr(children, "to_plotly_json"):
        yield from _walk(children)


def wall_component() -> html.Div:
    return html.Div(
        [
            html.Span("", id=WALL_BODY_ID, role="status"),
            html.Button("×", id="demo-wall-close", n_clicks=0, title="Dismiss", **{"aria-label": "Dismiss notice"}),
        ],
        id=WALL_ID,
        hidden=True,
        className="sfa-demo-wall",
    )


def decorate_layout(layout: Any, settings: DemoSettings) -> Any:
    caps = {
        "max-combos-input": settings.max_combos,
        "max-signals-slider": settings.max_signals_per_side,
        "grid-max-combos-input": settings.max_grid_combos,
        "bayesian-trials-input": settings.max_bayes_trials,
    }
    badge_done = False
    previous = None
    for node in _walk(layout):
        node_id = getattr(node, "id", None)
        if isinstance(node_id, str) and node_id in caps:
            cap = caps[node_id]
            node.max = cap
            if getattr(node, "value", None) is not None and node.value > cap:
                node.value = cap
            marks = getattr(node, "marks", None)
            if isinstance(marks, dict):
                node.marks = {k: v for k, v in marks.items() if int(k) <= cap}
        if not badge_done and getattr(node, "className", None) == "bbg-header-status-label":
            node.children = badge_text()
            if previous is not None and getattr(previous, "className", "") == "dot dot-up":
                previous.className = "dot dot-warn"
            badge_done = True
        previous = node
    if not badge_done:
        raise RuntimeError("header status label not found; the demo badge would be missing")
    # The root is a MantineProvider wrapping one Div; the wall goes into the
    # first container that holds a list. (A Dash component is itself
    # iterable -- over its descendants' ids -- so never list() one.)
    target = layout
    while not isinstance(getattr(target, "children", None), (list, tuple)):
        child = getattr(target, "children", None)
        if child is None or not hasattr(child, "to_plotly_json"):
            raise RuntimeError("no container with a children list to hold the demo wall")
        target = child
    target.children = [*target.children, wall_component()]
    return layout


def register_wall_close(app) -> None:
    app.clientside_callback(
        "function(n){ if(!n){ return window.dash_clientside.no_update; } return true; }",
        Output(WALL_ID, "hidden", allow_duplicate=True),
        Input("demo-wall-close", "n_clicks"),
        prevent_initial_call=True,
    )
