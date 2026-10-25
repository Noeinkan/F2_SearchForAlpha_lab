# Hosted workspace

**Live:** <https://alpha.noeinsolutions.com/> — the full research workspace,
for the owner and the people they invite. Not the public demo
(<https://alpha.demos.noeinsolutions.com/>, [DEMO.md](DEMO.md)).

| | Hosted workspace | Public demo |
|---|---|---|
| Code | `hosted/` (`python -m hosted.server`) | `demo/` |
| Deploy config | `.deploy-app/` — `bash deploy.sh` | `.deploy/` — `bash deploy-demo.sh` |
| Server slug | `alpha-lab` (`/opt/sites/alpha-lab/`) | `alpha` |
| Data | live Yahoo + SEC, Flow Scanner refresh on | frozen snapshot |
| Access | owner password + invited emails with a passcode | email code, 7-day trial |
| Explain (Gemini) | admins only | always off |
| Broker | absent (`lib/live/` deleted, no `ib_async`) | absent |

## Login

Modelled on Capsar (W3_capsar_io): nobody registers; the owner adds emails
to a whitelist and each person signs in with email + a passcode they were
mailed. Code: `hosted/login.py` (the gate), `hosted/users.py` (SQLite
whitelist at `state/hosted-users/users.sqlite3`, on the data volume),
`hosted/admin_users.py` (the `/admin/users` page).

Secrets in `/opt/sites/alpha-lab/.env`:

```
SITE_LOGIN_EMAIL=andrea.aita@noeinsolutions.com
SITE_LOGIN_PASSWORD_HASH=scrypt:32768:8:1$...
SITE_SECRET_KEY=<openssl rand -hex 32>        # signs the session cookie; required
ADMIN_EMAILS=andrea.aita@noeinsolutions.com   # comma list; unset = SITE_LOGIN_EMAIL only
GEMINI_API_KEY=...                            # optional: turns Explain on for admins
# NEO_SMTP_HOST / NEO_SMTP_PORT / NEO_SMTP_USER / NEO_SMTP_PASS / EMAIL_FROM:
# the same mail block as the demo, used to send invitations.
```

The owner's credential is the one that cannot be locked out by the database.
Its plain password lives only on the owner's PC, in
`~/.config/hetzner-site/owner-login.env`; the hetzner-site skill's "Owner
login" section has the one-line command that turns it into the hash line.
Without `SITE_LOGIN_EMAIL`, `SITE_LOGIN_PASSWORD_HASH` and `SITE_SECRET_KEY`
(32+ characters) the app refuses to start and the deploy rolls back.

**Inviting someone:** sign in, click **Users** in the header (or open
`/admin/users`), type the email, press *Add and email a passcode*. The
passcode is mailed and also shown once on the page, so it can be forwarded by
hand if the mail fails. The same page revokes, re-activates, issues a new
passcode or deletes. From a shell in the container:
`python -m hosted.users add|list|revoke|activate|regenerate|delete <email>`.

Admins are `ADMIN_EMAILS`, re-read on every request. Only an admin sees
**Users** and the **Explain** button; `/admin/users` and `/api/explain` answer
404 to anyone else.

Sessions last 14 days. The gate re-reads the person on every request, so a
revoked user is out on the next click; a new passcode (or a new owner
password, or a new `SITE_SECRET_KEY`) signs old sessions out. Five wrong tries
from one IP lock the form for 15 minutes. `/logout` signs out.

## Explain

Two ways to ask Gemini what something means; the answer comes in a popover,
in English:

- **Smart help per panel.** Every panel header (Market Data, Chart Settings,
  Execution Type, Trade Setup, Signals, the optimizer cards…) has a **✦**.
  Click it: the panel gets a dashed outline, a hint appears and whatever is
  under the pointer lights up. Then click anything inside the panel — a
  checkbox, a field, a button, the header itself — and it is explained
  instead of being clicked (no box gets ticked, no value changes). Esc, the ✦
  again or a click outside cancels.
- **Text selection.** Select a number or a word and press the **Explain**
  button that appears next to it.

Gemini receives the app's own definitions (`lib/explain/glossary.py`): the
metrics from `lib/metrics/names.py`, the indicator defaults from
`config/strategy_config.yaml`, and what each Buy/Sell signal means — only the
lines that match the clicked thing (`glossary_for`; ~850 prompt tokens instead
of ~3,500), or the bare vocabulary when nothing matches.

**Sources.** Each question is two Gemini calls made at the same time: the
answer, without search, and a short separate prompt with Google Search
(grounding) whose only job is the reference links. The text shows as soon as
it lands (measured 8–15 s; one combined grounded call took 18–26 s) and the
links slot in under it — usually they arrive first (~5–7 s). The popover lists
the sites plus Google's search-suggestion chips, which Google's grounding terms
require next to the links (shown in a sandboxed iframe, light or dark
following the browser's own mode). The search prompt carries only the clicked
text and the panel name, so one search serves a toggle, its label and every
ticker. `GEMINI_SEARCH=0` turns search off (no links, one call per question).

**Cache.** Good answers are stored in `state/explain-cache/answers.sqlite3`
(`SFA_EXPLAIN_CACHE`), keyed by model + full prompt, for 30 days. The symbol is
part of the prompt only when the selection is a number, so a control or an
indicator is asked once for every ticker. A cached answer returns at once,
shows "saved 25 Oct" (the day it was stored) and does not count against the rate limit; **↻ Refresh**
asks Gemini again and replaces the entry and its sources. The answer
comes back in a light format — `**bold**`, `` `code` ``, `- ` bullets and a
`$$ … $$` line for a formula in plain Unicode — which `95-explain.js` turns into
DOM nodes (never HTML), converting stray LaTeX to symbols. Admins only; locally (`python main.py`) you are
admin, and `main.py` reads `GEMINI_API_KEY` from the repo's `.env`.
`GEMINI_MODEL` overrides the default `gemini-flash-latest`. 20 answers and 20
searches a minute per user.

**Warming the cache.** `scripts/warm_explain_cache.py` asks every ✦ question
ahead of time, so clicks on controls answer at once. With the dashboard
running (`python main.py`), it opens it headless, opens every panel, asks
`95-explain.js` for each question a click could send — described exactly as a
click would, so the cache keys match — and fetches what is not cached yet.
Numbers are skipped (they change with every backtest). On the main page that is
~440 questions: ~440 answers and ~265 searches the first time, then only what
expired after 30 days or changed. `--dry-run` lists them, `--limit N` asks a
few, `--workers` sets how many at once (default 3). It writes the cache of the
machine it runs on: for the hosted site, run it there or copy the file to
`state/explain-cache/` on the volume. Grounded searches beyond Google's free
quota are billed: check *Google AI Studio → Billing* before a full run.

## What survives a redeploy

`state/`, `results/`, `export/` and `config/` live on the Docker volume
`workspace-data`, mounted at `/data` (`hosted/persist.py`). At every start
`config/` is refreshed from the repo, **except** `watchlists.json`,
`ui_presets.json` and `param_history.yaml`, which the dashboard edits. A
change to `config/strategy_config.yaml` therefore ships with a deploy, as in
the repo.

## Replaces

The older systemd service `searchforalpha-dashboard` (`/opt/searchforalpha`,
port 8060, `deploy.ps1`) served the workspace on the bare IP with no login.
It is stopped and disabled; its watchlists, presets and `state/` were copied
onto the volume.
