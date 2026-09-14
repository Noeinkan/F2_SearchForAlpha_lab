"""Empty states — what a region says before it has anything to show.

One builder, so the chart area, the backtest results and the signal list read
as the same kind of message: a glyph, a short title saying what is missing, and
a hint saying what to do about it. Styling lives in ``20-controls.css``
(``.sfa-empty-state``); the copy lives here so callbacks and layout share it.
"""

from __future__ import annotations

from dash import html

CHART_EMPTY_TITLE = "No chart yet"
CHART_EMPTY_HINT = "Pick a symbol with Ctrl + /, or open the command palette with Ctrl + K."

BACKTEST_EMPTY_TITLE = "No backtest yet"
BACKTEST_EMPTY_HINT = "Tick at least one buy and one sell signal above, then press RUN BACKTEST."

SIGNALS_NO_DATA_TITLE = "No signals yet"
SIGNALS_NO_DATA_HINT = "Signals appear once market data has loaded."

SIGNALS_NO_MATCH_TITLE = "No signals match"
SIGNALS_NO_MATCH_HINT = "Clear the search box or tick more categories."


def empty_state(
    title: str,
    hint: str | None = None,
    *,
    glyph: str = '◇',
    compact: bool = False,
    title_id: str | None = None,
    hint_id: str | None = None,
) -> html.Div:
    """A centred placeholder. ``compact`` drops the glyph and padding for narrow lists.

    ``title_id`` / ``hint_id`` let a clientside callback rewrite the text in
    place — the chart does, to show the reason its payload came back empty.
    """
    title_kwargs = {'id': title_id} if title_id else {}
    hint_kwargs = {'id': hint_id} if hint_id else {}
    children = []
    if not compact:
        children.append(html.Div(glyph, className='sfa-empty-state__glyph', **{'aria-hidden': 'true'}))
    children.append(html.Div(title, className='sfa-empty-state__title', **title_kwargs))
    if hint is not None or hint_id:
        children.append(html.Div(hint or '', className='sfa-empty-state__hint', **hint_kwargs))
    class_name = 'sfa-empty-state sfa-empty-state--compact' if compact else 'sfa-empty-state'
    return html.Div(children, className=class_name)
