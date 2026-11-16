"""sfa options-history: bulk download of end-of-day option chains from ThetaData."""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    group = typer.Typer(help="End-of-day option history archive (ThetaData, needs a running Theta Terminal).")
    app.add_typer(group, name="options-history")

    @group.command("download")
    def download_cmd(
        universe: Annotated[str, typer.Option("--universe", help="Comma list: sp500, nasdaq100.")] = "sp500,nasdaq100",
        tickers: Annotated[str | None, typer.Option("--tickers", help="Comma list of symbols; overrides --universe.")] = None,
        start: Annotated[str | None, typer.Option("--from", help="First date, YYYY-MM-DD. Default: the plan's first day.")] = None,
        end: Annotated[str | None, typer.Option("--to", help="Last date, YYYY-MM-DD. Default: yesterday.")] = None,
        refresh: Annotated[bool, typer.Option("--refresh", help="Refetch months already archived.")] = False,
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """Archive every contract's daily bid/ask for each symbol, one month per file; safe to stop and rerun."""
        from lib.options import history_archive, theta_history

        first, last = theta_history.history_window()
        start_day = max(date.fromisoformat(start), first) if start else first
        end_day = min(date.fromisoformat(end), last) if end else last
        symbols = ([history_archive.theta_symbol(t) for t in tickers.split(",") if t.strip()] if tickers
                   else history_archive.universe(universe.split(",")))
        months = len(history_archive.month_ranges(start_day, end_day))
        if not json_output:
            minutes = len(symbols) * (months + 1) * theta_history.MIN_INTERVAL_SECONDS / 60
            typer.echo(f"{len(symbols)} symbols × {months} months, {start_day} → {end_day}. "
                       f"Up to ~{minutes / 60:.1f} h at one request every {theta_history.MIN_INTERVAL_SECONDS:g} s; "
                       "months already archived are skipped.")

        def progress(position: int, total: int, result) -> None:
            if json_output:
                return
            detail = (f"failed: {result.error}" if result.error else
                      f"{result.months_fetched} fetched, {result.months_skipped} skipped, {result.rows:,} rows")
            typer.echo(f"[{position}/{total}] {result.symbol}: {detail}")

        summary = history_archive.download(symbols, start_day, end_day, refresh=refresh, progress=progress)
        payload = summary.as_dict()
        if json_output:
            typer.echo(json.dumps(payload))
        else:
            typer.echo(f"Done: {payload['rows']:,} rows, {len(payload['failed'])} failed"
                       + (f" ({', '.join(payload['failed'])})" if payload["failed"] else "") + ".")
            if summary.stopped:
                typer.echo(f"Stopped early: {summary.stopped}")
        if summary.stopped:
            raise typer.Exit(code=2)

    @group.command("status")
    def status_cmd(
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """List archived symbols with the months held."""
        from lib.options import history_archive

        rows = history_archive.status()
        if json_output:
            typer.echo(json.dumps(rows))
            return
        if not rows:
            typer.echo("Archive is empty. Run: sfa options-history download")
            return
        for row in rows:
            typer.echo(f"{row['symbol']:<8} {row['months']:>3} months  {row['first']} → {row['last']}")
        typer.echo(f"{len(rows)} symbols")
