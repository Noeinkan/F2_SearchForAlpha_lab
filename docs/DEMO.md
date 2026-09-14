# Public demo

**Live:** <https://alpha.demos.noeinsolutions.com/> — a free 7-day trial with a
verified email, nothing to install.

The demo is the research terminal running on a **frozen snapshot**: charts,
indicators, all three backtest modes, the signal-combination optimiser, grid
search, the Bayesian sweep, walk-forward validation and the fundamentals
workspace all work. What it cannot do is reach the outside world (except the
one mail server that sends sign-in codes) or place an order.

## What is different from the workspace

| | Workspace (`python main.py`) | Public demo (`python -m demo.server`) |
|---|---|---|
| Prices | Yahoo Finance, live | `demo/fixtures/ohlcv/`, frozen at the **11 Sep 2026** close |
| Fundamentals | SEC EDGAR + Yahoo, live | `demo/fixtures/fundamentals/`, frozen at the same close |
| Tickers | ~13k in the symbol search | 12: TSLA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, KO, XOM, SPY, QQQ |
| History | everything Yahoo serves | daily bars from 2006 (or listing), hourly bars for the last two years |
| Broker / paper trading / live mode | `sfa run` against an IB Gateway | **absent**: `ib_async` not installed, `lib/live/` deleted from the image, importing it refused |
| Flow Scanner | live options chains | off (it needs a live chain) |
| Presets, watchlists | saved to `config/` | kept in the visitor's browser only |
| State | one user, one process | one in-memory state per visitor, dropped after 30 idle minutes |
| Access | anyone at the keyboard | a verified email; 7 days from the first sign-in |

The page says so itself: the header's status label reads
`DEMO · DATA 11 SEP 2026`, and a dismissible banner states what is frozen,
what is switched off, who is signed in and until when.

## Access: email sign-in, trial, usage

Without this, anyone could use the demo forever and nobody would know who
did. So every page and every callback sits behind a sign-in (`demo/access/`):

1. A visitor without an access cookie is sent to `/access` and types an email.
2. The demo emails a **6-digit code and a link**, both good once, for 15
   minutes. The link opens a confirm button rather than signing in straight
   away, because corporate mail scanners open every link in an email and
   would otherwise use it up before the person clicks.
3. The first sign-in starts the **trial: 7 days**. After that, pages go to a
   "your free trial has ended — write to …" page and a running dashboard shows
   the same message as a notice. Asking for a new code with that address
   emails the "ended" note instead of a code, so the page never reveals which
   addresses have had a trial.
4. While the trial runs, **25 optimiser runs per person per day** (UTC), on
   top of the per-IP limits below.

One trial per mailbox, not per spelling: `Jane.Doe+demo@gmail.com` and
`janedoe@gmail.com` are the same person (`+tags` dropped everywhere, dots
dropped for Gmail). Well-known throwaway-inbox domains are refused
(`demo/access/emails.py`). Someone determined can still use a second real
mailbox; that is the ceiling of what email can do.

The sign-in page states what is stored (email, sign-in times, IP address,
features used), why, and that it is deleted 12 months after the last visit or
on request. An address that was never verified — anyone can type anyone's
address — is deleted after 30 days. Nothing is sent to anyone else.

### What is recorded, and where to read it

Every signed-in request is logged against the email in SQLite
(`DEMO_ACCESS_DB`, on the `access-data` Docker volume so it survives restarts
and redeploys): page loads, backtests, data loads, fundamentals loads,
optimiser runs, limits hit, sign-ins.

**`/admin`** shows it. To open it:

1. Go to <https://alpha.demos.noeinsolutions.com/admin>. With no
   `DEMO_ADMIN_TOKEN` configured this is a 404 — see "Deploying the gate".
2. Paste the admin token into the **Admin token** box and press **Open**. You
   stay signed in for 12 hours on that browser. Five wrong tries lock the form
   for 15 minutes.
3. The page shows totals (signed up, trials running, new and seen this week,
   backtests this week, optimiser runs today), then one row per person —
   status, sign-up date, access end, last seen, active days, page loads,
   backtests, optimiser runs, data and fundamentals loads, limits hit, the
   tickers they looked at most, last IP — and the latest 100 events.
4. Per person: **+7 days** (extends from today or from the current end,
   whichever is later, and lifts a revoke), **Revoke** (signs them out
   everywhere at once), **Delete** (removes the person and all their usage;
   use it for a deletion request).
5. **Visitors CSV** and **Events CSV** (top right) download everything for a
   spreadsheet.

### Deploying the gate

The mail account and the admin token are secrets, so they go only in
`/opt/sites/alpha/.env` on the server, never in the repo. The demo **refuses
to start** without the mail host, user and password; the deploy's health
check then fails and `site-deploy.sh` rolls back to the previous version, so a
missing secret costs a failed deploy, not an outage.

**The mail account is Neo**, the host of noeinsolutions.com mail, and the same
mailbox Capsar (W3_capsar_io) already sends its codes from — with the same
variable names, so its lines are copied as they are. Nothing needs setting up
at the provider or in DNS: the domain already publishes Neo's SPF record
(`include:spf0001.neo.space`) and a Neo DKIM key (selector `neo1`), which is
what gets the codes into inboxes.

**Visitors only ever see `support@noeinsolutions.com`**: it is the sender of
the code emails (`SearchForAlpha Lab demo <support@noeinsolutions.com>`) and
the contact on the sign-in and trial-ended pages. The owner's own address is
only the Neo *login*. Neo lets a mailbox send as another address only when that
address is an **alias** of the mailbox; otherwise it answers "553 Sender
address rejected: not owned by user", and every code fails. The start-up mail
check offers the sender to Neo without sending anything, so a missing alias
shows up in the log as "NOT usable … add that address as an alias".

Neo lets one mailbox send about 1,000 emails a day, and that budget is shared
with your own mail and with Capsar's. The demo stops sending sign-in codes
after `DEMO_CODES_PER_DAY` (200) in any 24 hours; a visitor past that sees "the
demo is sending a lot of sign-in emails right now".

1. **Make `support@` an alias of the mailbox, once.** Sign in to Neo Webmail
   with the mailbox you log in with (or to the Neo Email Control Panel as the
   domain admin), open the mailbox's **email alias** settings and add
   `support@noeinsolutions.com`. Neo allows up to 10 aliases a mailbox. Mail to
   support@ then lands in that mailbox, and the mailbox may send as support@.
   Neo's own walkthrough: <https://support.neo.space/hc/en-us/articles/14465294068761-Email-Alias>.
   *If support@ already exists as a separate mailbox, Neo will not let you
   reuse the name as an alias; either delete that mailbox first or log the
   demo in as support@ with its own password instead. A forwarder will not do:
   it receives but cannot send.*
2. **Copy the mail lines from Capsar.** Open
   `C:\Users\andre\Downloads\W3_capsar_io\.env` and copy the four lines
   starting with `NEO_SMTP_HOST`, `NEO_SMTP_PORT`, `NEO_SMTP_USER` and
   `NEO_SMTP_PASS`. They read `smtp0001.neo.space`, `465`, the mailbox address
   and its password. **Change `465` to `587` for the server**: Hetzner blocks
   outgoing connections on port 465 (and 25), so a send on 465 waits and times
   out. Port 587 starts plain and switches to encryption before the password
   is sent (STARTTLS), and the demo picks that up from the port. Add
   `EMAIL_FROM=support@noeinsolutions.com` yourself (Capsar's says the owner's
   address).
3. **Make an admin token**, at least 24 characters:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Keep it in
   your password manager.
4. **Write the secrets on the server.** Paste the lines from step 2 and the
   token in place of the placeholders:

   ```bash
   ssh root@77.42.70.26
   cat >> /opt/sites/alpha/.env <<'EOF'
   NEO_SMTP_HOST=smtp0001.neo.space
   NEO_SMTP_PORT=587
   NEO_SMTP_USER=the-mailbox-address
   NEO_SMTP_PASS='the-mailbox-password'
   EMAIL_FROM=support@noeinsolutions.com
   DEMO_ADMIN_TOKEN=the-token-from-step-3
   EOF
   chmod 600 /opt/sites/alpha/.env
   ```

   **Keep the single quotes around the password.** Docker Compose reads a `$`
   in this file as the start of a variable name, so a password containing `$`
   reaches the demo cut short and Neo answers "535 authentication failed";
   quoted, it arrives exactly as written.
   *If the Neo password is ever changed, Capsar and the demo both stop sending
   until this file and Capsar's `.env` are updated.*
5. **Deploy**: commit, push, then `bash deploy-demo.sh` from the repo root.
6. **Check it**: open the demo in a private window — it should land on the
   sign-in page. Sign in with your own address; the email should arrive within
   a minute, from support@noeinsolutions.com. Then open `/admin` and find
   yourself in the table.
   *If the page says "The sign-in email could not be sent", read the log:
   `ssh root@77.42.70.26 "docker logs site-alpha-web 2>&1 | grep 'demo access'"`.
   Right after every start the demo signs in to the mail server once and
   writes either "mail server … reachable" or "NOT usable" with the reason.
   "timed out" means a blocked port; "535" means a wrong user or password;
   "553 … not owned" means support@ is not yet an alias of the mailbox.*

To change the numbers, edit the `DEMO_*` values in `.deploy/compose.yml` and
redeploy. To reach the gate without mail on your own machine, see "Run it
locally".

## Limits

Every limit is an environment variable; the defaults live in
`demo/settings.py` and the running values in `.deploy/compose.yml`.

| Variable | Default | What it caps |
|---|---|---|
| `DEMO_MAX_COMBOS` | 150 | combinations per signal-combination search |
| `DEMO_MAX_SIGNALS_PER_SIDE` | 2 | signals stacked per side in that search |
| `DEMO_MAX_GRID_COMBOS` | 250 | combinations per parameter grid search (the workspace default; narrow the parameters when a bundle's grid is larger) |
| `DEMO_MAX_BAYES_TRIALS` | 30 | trials per Bayesian sweep |
| `DEMO_OPTIMIZER_WORKERS` | 2 | threads the combination search shares, all visitors together |
| `DEMO_MAX_CONCURRENT_JOBS` | 2 | optimiser runs in flight at once, all visitors together |
| `DEMO_JOB_TIMEOUT_SECONDS` | 120 | a run still going after this is stopped (the combination search ranks what finished) |
| `DEMO_ACTIONS_PER_IP_PER_MINUTE` | 30 | backtests, data loads and fundamentals loads per IP |
| `DEMO_JOBS_PER_IP_PER_HOUR` | 20 | optimiser runs started per IP |
| `DEMO_MAX_SESSIONS` | 60 | visitor states held in memory (oldest evicted) |
| `DEMO_SESSION_IDLE_MINUTES` | 30 | idle visitor state is dropped after this |
| `DEMO_ACCESS_GATE` | true | the email gate and usage log; `false` opens the demo to anyone, unrecorded (local runs only) |
| `DEMO_TRIAL_DAYS` | 7 | access from the first sign-in |
| `DEMO_JOBS_PER_EMAIL_PER_DAY` | 25 | optimiser runs per person per UTC day |
| `DEMO_RETENTION_DAYS` | 365 | a person unseen this long is deleted with their usage |
| `DEMO_CODE_MINUTES` | 15 | life of a sign-in code and link |
| `DEMO_CODE_ATTEMPTS` | 5 | wrong codes before that code stops working |
| `DEMO_CODES_PER_EMAIL_PER_HOUR` | 3 | sign-in emails to one address |
| `DEMO_CODES_PER_HOUR` | 60 | sign-in emails in total (keeps inside the mail plan) |
| `DEMO_SIGNUPS_PER_IP_PER_DAY` | 5 | new addresses from one connection |
| `DEMO_BLOCKED_EMAIL_DOMAINS` | — | extra throwaway domains to refuse, comma-separated |
| `DEMO_ACCESS_DB` | `state/demo-access/access.sqlite3` | the SQLite file (`/app/data/…` on the volume in production) |
| `DEMO_PUBLIC_URL` | request host | base of the link in the email |
| `DEMO_CONTACT_EMAIL` | `SFA_FEEDBACK_EMAIL` | shown on the privacy note and the trial-ended page |
| `DEMO_MAIL_BACKEND` | smtp | `console` logs the email instead of sending it |
| `DEMO_CODES_PER_DAY` | 200 | sign-in emails in total per 24 hours (a fifth of the Neo mailbox's daily budget) |
| `NEO_SMTP_HOST` / `_PORT` / `_USER` / `_PASS`, `EMAIL_FROM` | — / 587 / — / — / the user | the Neo mail account, same names as Capsar; `SMTP_*` / `SMTP_FROM` read when unset (server `.env` only) |
| `DEMO_SMTP_SECURITY` | auto | `auto` is implicit TLS on 465 and STARTTLS otherwise; or `ssl`, `starttls`, `none` |
| `DEMO_ADMIN_TOKEN` | — | unlocks `/admin`; under 24 characters and `/admin` is a 404 (server `.env` only) |

Under those, the container is capped at **2 CPUs and 1.5 GB** (`cpus` and
`mem_limit` in `.deploy/compose.yml`), so the demo can never take more than a
quarter of the server whatever visitors do. Grid search, the Bayesian sweep and
walk-forward validation are one-at-a-time in the dashboard; in the demo only
the visitor who started one can poll or stop it.

A limit that refuses a request shows a notice under the header — what ran out,
when it resets — and changes nothing else. The date range is capped by the
snapshot itself.

## Run it locally

```bash
# PowerShell: $env:DEMO_MODE = "true"; python -m demo.server
DEMO_MODE=true python -m demo.server        # http://127.0.0.1:8050/ticker/TSLA
```

**The repo's `.env` is read at start** (`demo/envfile.py`), so the mail lines
and `DEMO_ADMIN_TOKEN` written there are used: codes really go out from the Neo
mailbox, and `/admin` opens with that token. A variable set in the terminal
wins over the same one in `.env`. From a laptop `NEO_SMTP_PORT=465` works; the
server needs 587. The start-up log says which settings it read and whether the
mail server accepted the sign-in.

Without a mail account, add `DEMO_MAIL_BACKEND=console`: the sign-in email,
code included, is printed in the terminal instead of sent. Add
`DEMO_ACCESS_GATE=false` to skip the gate altogether.

It needs only the packages in `demo/requirements.txt` (a subset of `uv.lock`
without `ib_async`, plus `waitress`). The workspace's own environment has no
`waitress`; then the demo says so and serves with Flask's development server,
which it allows on `127.0.0.1` only.

## Kill switch

`DEMO_MODE` defaults off. Unset or `false`, `demo.server` answers **404 on
every page** (and `200 {"demo": false}` on `/healthz`, so the container stays
healthy) and never imports the dashboard. It does not fall back to the live,
unguarded workspace. The usage database is untouched and comes back with the
demo.

To take the public demo down: set `DEMO_MODE: "false"` in `.deploy/compose.yml`,
commit, push, `bash deploy-demo.sh`. To remove the site entirely:
`bash C:/Personal_utilities/hetzner-site/bin/site-remove.sh alpha`.

## How it is put together

Everything lives in `demo/`; the workspace carries no demo branches. The one
change to `lib/` is `create_app()` in `lib/dash/integrated_dashboard.py`, which
builds the app without serving it so a WSGI server can.

| Module | Job |
|---|---|
| `demo/server.py` | entry point; seals, patches, builds, wraps, serves with waitress |
| `demo/sealing.py` | refuses outbound sockets, `yfinance`, and imports of `lib.live` / IB clients |
| `demo/patches.py` | swaps the data seams (`_yahoo_history`, `fetch_fundamentals`, quotes, universe, disk cache, preset/watchlist writes, Flow Scanner) for the snapshot |
| `demo/sessions.py` | replaces the process-wide `dashboard_state` with a per-visitor proxy (session cookie) |
| `demo/limits.py` | per-IP sliding-window limits and the optimiser-run gate |
| `demo/guards.py` | wraps the callbacks that start CPU work: caps, limits, gate, notices |
| `demo/banner.py` | header badge, banner (with the signed-in line), the refusal notice, input `max` values |
| `demo/snapshot.py` | reads `demo/fixtures/` |
| `demo/freeze_demo_data.py` | writes `demo/fixtures/` (the only part that uses the network) |
| `demo/access/gate.py` | the sign-in routes and the check in front of every page and callback |
| `demo/access/store.py` | SQLite: visitors, sign-in codes (hashed), browser grants, usage events |
| `demo/access/mailer.py` | sends the sign-in email over SMTP, or prints it |
| `demo/access/pages.py` | the sign-in pages and the two emails |
| `demo/access/admin.py` | `/admin` and the CSV exports |
| `demo/access/emails.py` | address validation, one-trial-per-mailbox normalisation, throwaway blocklist |

Tests: `python -m pytest lib/tests/test_demo_mode.py lib/tests/test_demo_access.py` — the kill switch, both
seals and the single mail-server exception, the snapshot, the limiter and gate, per-visitor isolation, the
sign-in flow (code, link, wrong codes, expiry, rate limits, throwaway domains, one trial per mailbox), the
trial ending, the daily cap, `/admin` (token, CSV, extend/revoke/delete, escaping), and an end-to-end run of
the demo in a subprocess (signed-out redirect, sign-in, a backtest on the snapshot, a rate-limit notice, a
clamped optimiser run, a second visitor refused, a shared job its owner alone can stop, usage recorded per
email, the broker import refused).

## The snapshot

- **Snapshot:** 11 Sep 2026 close. **Captured:** 14 Sep 2026.
- **Bars:** Yahoo Finance via `yfinance`, split- and dividend-adjusted, exactly
  as `lib.data_processing._yahoo_history` returns them. 4,076–5,205 daily bars
  and 3,466 hourly bars per ticker.
- **Fundamentals:** the payload `lib.fundamentals.fetch_fundamentals` returns —
  SEC EDGAR XBRL for statements (XOM fell back to Yahoo statements), Yahoo for
  analyst estimates — with *now* pinned to the snapshot close and the quote
  fields rewritten from the frozen daily bars, so the fundamentals price
  matches the chart. SPY and QQQ have none (ETFs file no 10-K).
- **Size:** about 2.4 MB, committed.

### Refresh it

```bash
python -m demo.freeze_demo_data --snapshot YYYY-MM-DD   # a completed session
python -m pytest lib/tests/test_demo_mode.py
DEMO_MODE=true python -m demo.server                    # look at the numbers on screen
```

Then update the dates in this file, `demo/demo.json` and the landing card's
note, commit `demo/fixtures/`, push and `bash deploy-demo.sh`. Retake the
landing captures with
`node C:/Personal_utilities/screenshot-kit/shotkit.mjs --config demo/shotkit.demo.config.mjs`.
