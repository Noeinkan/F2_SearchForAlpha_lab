"""Helpers for research-universe briefing and seeded ETF exploration."""

from __future__ import annotations

import random
from typing import Any


def _as_str_list(value: Any) -> list[str]:
    return [str(item) for item in list(value or [])]


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def get_ticker_universe(research: dict[str, Any]) -> dict[str, list[str]]:
    raw = research.get("ticker_universe", {}) or {}
    return {str(name): _as_str_list(symbols) for name, symbols in raw.items()}


def get_etf_universe_groups(ticker_universe: dict[str, list[str]]) -> list[str]:
    return [name for name in ticker_universe if name.startswith("etf_")]


def build_exploration_config(research: dict[str, Any]) -> dict[str, Any]:
    exploration_cfg = research.get("exploration", {}) or {}
    return {
        "enabled": bool(exploration_cfg.get("enabled", False)),
        "mode": str(exploration_cfg.get("mode", "seeded_stratified")),
        "benchmark_groups": _dedupe_preserve(
            _as_str_list(
                exploration_cfg.get(
                    "benchmark_groups",
                    ["etf_broad", "etf_fixed_income", "etf_commodity_physical"],
                )
            )
        ),
        "eligible_groups": _dedupe_preserve(
            _as_str_list(
                exploration_cfg.get(
                    "eligible_groups",
                    [
                        "etf_sector",
                        "etf_style_factor",
                        "etf_international",
                        "etf_commodity_equity_linked",
                    ],
                )
            )
        ),
        "excluded_groups": _dedupe_preserve(
            _as_str_list(exploration_cfg.get("excluded_groups", ["etf_commodity_futures"]))
        ),
        "seeds": [int(seed) for seed in list(exploration_cfg.get("seeds", [11, 23, 47]) or [])],
        "sample_per_group": max(1, int(exploration_cfg.get("sample_per_group", 1))),
        "max_random_tickers": max(0, int(exploration_cfg.get("max_random_tickers", 4))),
        "advisory_only": bool(exploration_cfg.get("advisory_only", True)),
    }


def get_etf_group_roles(
    ticker_universe: dict[str, list[str]],
    benchmark_groups: list[str],
) -> dict[str, str]:
    benchmark_set = set(benchmark_groups)
    return {
        name: ("benchmark" if name in benchmark_set else "specialist")
        for name in get_etf_universe_groups(ticker_universe)
    }


def flatten_group_tickers(
    ticker_universe: dict[str, list[str]],
    groups: list[str],
) -> list[str]:
    flattened: list[str] = []
    for group in groups:
        flattened.extend(ticker_universe.get(group, []))
    return _dedupe_preserve(flattened)


def get_effective_exploration_groups(
    ticker_universe: dict[str, list[str]],
    exploration: dict[str, Any],
) -> tuple[list[str], list[str]]:
    etf_groups = set(get_etf_universe_groups(ticker_universe))
    benchmark_groups = [group for group in exploration["benchmark_groups"] if group in etf_groups]
    excluded_groups = set(exploration["excluded_groups"])
    eligible_groups = [
        group
        for group in exploration["eligible_groups"]
        if group in etf_groups and group not in excluded_groups and group not in benchmark_groups
    ]
    return benchmark_groups, eligible_groups


def materialize_seed_samples(
    ticker_universe: dict[str, list[str]],
    benchmark_tickers: list[str],
    eligible_groups: list[str],
    exploration: dict[str, Any],
) -> list[dict[str, Any]]:
    seed_samples: list[dict[str, Any]] = []

    for seed in exploration["seeds"]:
        shuffled_by_group: dict[str, list[str]] = {}
        for group in eligible_groups:
            tickers = [
                ticker
                for ticker in _dedupe_preserve(ticker_universe.get(group, []))
                if ticker not in benchmark_tickers
            ]
            rng = random.Random(f"{seed}:{group}")
            rng.shuffle(tickers)
            shuffled_by_group[group] = tickers

        sampled_groups: dict[str, list[str]] = {group: [] for group in eligible_groups}
        random_tickers: list[str] = []

        for _ in range(exploration["sample_per_group"]):
            for group in eligible_groups:
                if len(random_tickers) >= exploration["max_random_tickers"]:
                    break
                group_pool = shuffled_by_group[group]
                if not group_pool:
                    continue
                ticker = group_pool.pop(0)
                sampled_groups[group].append(ticker)
                random_tickers.append(ticker)
            if len(random_tickers) >= exploration["max_random_tickers"]:
                break

        sampled_groups = {group: tickers for group, tickers in sampled_groups.items() if tickers}
        seed_samples.append(
            {
                "seed": seed,
                "sampled_groups": sampled_groups,
                "random_tickers": random_tickers,
                "all_tickers": benchmark_tickers + [
                    ticker for ticker in random_tickers if ticker not in benchmark_tickers
                ],
            }
        )

    return seed_samples