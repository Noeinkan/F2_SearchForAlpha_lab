"""sfa instructions: emit a compact agent briefing for OpenClaw."""

from __future__ import annotations

import json
from typing import Annotated

import typer
import yaml


def _load_research_cfg() -> dict:
    try:
        with open("config/agent.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _build_briefing(cfg: dict) -> dict:
    research = cfg.get("research", {})
    stm = research.get("single_target_mode", {})
    promotion = cfg.get("promotion", {})
    windows = research.get("backtest_windows", {})
    ticker_universe = research.get("ticker_universe", {})
    etf_universe_groups = [name for name in ticker_universe if name.startswith("etf_")]

    mode = "single_target" if stm.get("enabled") else "sweep"
    target = stm.get("ticker", "SPY")
    win_key = stm.get("window", "in_sample")
    win = windows.get(win_key, {})

    rules: list[str] = [
        "--name is always the strategy bundle name; use --ticker to override the target symbol",
        "pass --json to every command; treat non-zero exit as error",
        "never invent strategy names - use sfa list to discover them",
        "pause and summarise after every 3 backtests",
        "flag overfitting: optimised window <5 bars OR >50% of training period",
        f"promote gate: oos_sharpe_mean>={promotion.get('min_oos_sharpe_mean', 1.0)}, "
        f"degradation<={promotion.get('max_degradation', 0.4)}, "
        f"walkforward_age<={promotion.get('walkforward_max_age_days', 7)}d",
        "metric selection: SPY>SMA200 -> sortino; ranging/sideways -> calmar",
    ]

    if mode == "single_target":
        rules.insert(0,
            f"SINGLE_TARGET MODE: run ALL strategies vs {target} "
            f"on window {win_key} ({win.get('from','?')} -> {win.get('to','?')}) "
            "before any cross-ticker expansion"
        )
        rules.insert(
            1,
            "prefer `sfa sweep-single` when the task is to test every strategy on the fixed target ticker",
        )
    else:
        rules.insert(0,
            "SWEEP MODE: start with liquid benchmark ETF groups; expand to sector or specialist ETFs only if Sortino>1.5 on 2+ benchmark ETFs"
        )
        rules.insert(
            1,
            "treat futures-based commodity ETFs as second-pass research because roll yield and curve shape can dominate returns",
        )

    backtest_syntax = "sfa backtest --name NAME --from YYYY-MM-DD --to YYYY-MM-DD --json"
    if mode == "single_target":
        backtest_syntax = (
            f"sfa backtest --name NAME --ticker {target} --from YYYY-MM-DD --to YYYY-MM-DD --json"
        )

    loop = [
        "1:list -> discover strategies",
        "2:backtest -> sanity-check live_params on the selected strategy bundle",
        "3:optimise --metric <sortino|calmar|sharpe|composite> -> TPE study",
        "4:trials --top 10 -> inspect leaderboard",
        "5:walkforward --params <trial_id> -> OOS validation",
        "6:promote --trial <id> -> gate-check + write live_params",
        "7:run --mode paper -> start runner",
        "8:status / kill -> observe / stop",
    ]
    if mode == "single_target":
        loop[1] = "2:sweep-single -> sanity-check all strategy bundles on the selected target ticker"

    return {
        "mode": mode,
        "etf_universe_groups": etf_universe_groups,
        **({"target": target, "window": win_key,
            "from": win.get("from"), "to": win.get("to")} if mode == "single_target" else {}),
        "loop": loop,
        "rules": rules,
        "syntax": {
            "list":        "sfa list --json",
            "backtest":    backtest_syntax,
            "sweep-single": "sfa sweep-single --ticker SYMBOL --from YYYY-MM-DD --to YYYY-MM-DD --json",
            "optimise":    "sfa optimise --name NAME --trials N --metric METRIC --json",
            "trials":      "sfa trials --name NAME --top 10 --json",
            "walkforward": "sfa walkforward --name NAME --params TRIAL_ID --json",
            "promote":     "sfa promote --name NAME --trial TRIAL_ID --json",
            "run":         "sfa run --name NAME --mode paper --json",
            "status":      "sfa status --json",
            "kill":        "sfa kill --name NAME --json",
            "instructions": "sfa instructions --json",
        },
    }


def register(app: typer.Typer) -> None:
    @app.command("instructions")
    def instructions(
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """Emit a compact agent briefing (run this at the start of every session)."""
        cfg = _load_research_cfg()
        briefing = _build_briefing(cfg)

        if json_output:
            typer.echo(json.dumps(briefing, indent=2, ensure_ascii=False))
            return

        typer.echo(f"MODE: {briefing['mode'].upper()}")
        if briefing["mode"] == "single_target":
            typer.echo(
                f"TARGET: {briefing['target']}  WINDOW: {briefing['window']} "
                f"({briefing['from']} -> {briefing['to']})"
            )
        typer.echo("\nLOOP:")
        for step in briefing["loop"]:
            typer.echo(f"  {step}")
        typer.echo("\nRULES:")
        for rule in briefing["rules"]:
            typer.echo(f"  - {rule}")
        typer.echo("\nSYNTAX:")
        for cmd, syn in briefing["syntax"].items():
            typer.echo(f"  {cmd:15s} {syn}")
