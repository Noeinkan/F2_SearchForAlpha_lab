"""Fill the Explain cache ahead of time, so ✦ clicks on controls answer at once.

A control, a label or a panel header means the same on every ticker, so its
answer can be fetched once and served from the cache (``lib/explain/cache.py``)
for 30 days. This script opens the running dashboard in a headless browser,
asks ``95-explain.js`` for every question a ✦ click could ask on each page --
described exactly as a real click would, so the cache keys match -- and asks
Gemini for the ones not cached yet: the answer and the sources, as the popover
does. Numbers are skipped: they change with every backtest.

    python main.py                                   # in another terminal
    python scripts/warm_explain_cache.py --dry-run   # list what it would ask
    python scripts/warm_explain_cache.py             # ask (minutes; see the count first)

The answers go to the cache file this machine uses (``SFA_EXPLAIN_CACHE``,
default ``state/explain-cache/answers.sqlite3``). For the hosted site, run it
on the server (or copy the file onto its ``state/`` volume).
Needs ``GEMINI_API_KEY`` (read from ``.env`` like ``main.py``) and Playwright.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DEFAULT_URL = "http://127.0.0.1:8050"
DEFAULT_PAGES = ["/"]


def collect(url: str, pages: list[str]) -> list[dict]:
    """Every ✦ question on the given pages, from the browser script itself."""
    from playwright.sync_api import sync_playwright

    items, seen = [], set()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        for path in pages:
            page.goto(url.rstrip("/") + path, wait_until="networkidle", timeout=120_000)
            try:
                page.wait_for_function("() => window.sfaExplainWarmup", timeout=30_000)
            except Exception:
                sys.exit("Explain is not on for this browser: is the server local (admin) and GEMINI_API_KEY set?")
            page.wait_for_timeout(2_000)  # panels that mount late
            page.evaluate("() => window.sfaExplainWarmup.openAllPanels()")
            page.wait_for_timeout(2_000)  # accordions finish opening
            for item in page.evaluate("() => window.sfaExplainWarmup.list()"):
                key = (item["selection"], item["context"], item["page"])
                if key not in seen:
                    seen.add(key)
                    items.append(item)
        browser.close()
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default=DEFAULT_URL, help=f"running dashboard (default {DEFAULT_URL})")
    parser.add_argument("--page", action="append", dest="pages",
                        help="path to visit, repeatable (default: /, which lands on the last ticker)")
    parser.add_argument("--workers", type=int, default=3, help="questions asked at the same time (default 3)")
    parser.add_argument("--limit", type=int, default=0, help="ask at most this many (0 = all)")
    parser.add_argument("--fresh", action="store_true", help="ask again even when cached")
    parser.add_argument("--dry-run", action="store_true", help="only list the questions and what is cached")
    args = parser.parse_args()

    from main import _load_local_env

    _load_local_env()
    from lib.explain import gemini
    from lib.explain.cache import AnswerCache

    if not gemini.is_configured() and not args.dry_run:
        print("GEMINI_API_KEY is not set (environment or .env).")
        return 1

    items = collect(args.url, args.pages or DEFAULT_PAGES)
    cache = AnswerCache.from_env()
    parts = list(gemini.PARTS) if gemini.search_enabled() else ["answer"]
    jobs, keys, cached = [], set(), 0
    for item in items:
        question = (item["selection"], item["context"], "", item["page"])
        for part in parts:
            key = gemini.cache_key(*question, part=part)
            if key in keys:  # e.g. one search serves a toggle and its label
                continue
            keys.add(key)
            if args.fresh or cache.get(key) is None:
                jobs.append((item, part, key, question))
            else:
                cached += 1

    panels = sorted({i["panel"] for i in items})
    answers = sum(1 for job in jobs if job[1] == "answer")
    print(f"{len(items)} questions in {len(panels)} panels; {len(jobs)} calls to make "
          f"({answers} answers, {len(jobs) - answers} searches; {cached} already cached). Cache: {cache.path}")
    if args.dry_run:
        for item in items:
            print(f"  [{item['panel']}] {item['selection'][:70]}")
        return 0
    if args.limit:
        jobs = jobs[: args.limit]

    def run(job):
        item, part, key, question = job
        result = gemini.explain(*question) if part == "answer" else gemini.find_sources(item["selection"], item["context"])
        if result.ok:
            cache.put(key, item["selection"], result)
        return job, result

    started, failed = time.monotonic(), 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for n, future in enumerate(as_completed(futures), 1):
            (item, part, _, _), result = future.result()
            skipped = not result.ok and result.text.startswith("No sources")  # Gemini did not search
            mark = "ok " if result.ok else ("-- " if skipped else "ERR")
            failed += not result.ok and not skipped
            print(f"{n:>4}/{len(jobs)} {mark} {part:<7} [{item['panel']}] {item['selection'][:50]}"
                  + ("" if result.ok else f" -- {result.text}"), flush=True)
            if not result.ok and "quota" in result.text:
                print("Quota reached: stopping. Run it again later; what is cached stays cached.")
                for f in futures:
                    f.cancel()
                break
    print(f"Done in {time.monotonic() - started:.0f} s, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
