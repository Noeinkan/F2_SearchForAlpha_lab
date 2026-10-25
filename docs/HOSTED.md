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
`config/strategy_config.yaml`, and what each Buy/Sell signal means. The answer
comes back in a light format — `**bold**`, `` `code` ``, `- ` bullets and a
`$$ … $$` line for a formula in plain Unicode — which `95-explain.js` turns into
DOM nodes (never HTML), converting stray LaTeX to symbols. Admins only; locally (`python main.py`) you are
admin, and `main.py` reads `GEMINI_API_KEY` from the repo's `.env`.
`GEMINI_MODEL` overrides the default `gemini-flash-latest`. 20 requests a
minute per user.

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
