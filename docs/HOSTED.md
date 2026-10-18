# Hosted workspace

**Live:** <https://alpha.noeinsolutions.com/> — the full research workspace,
for the owner only. Not the public demo (<https://alpha.demos.noeinsolutions.com/>,
[DEMO.md](DEMO.md)).

| | Hosted workspace | Public demo |
|---|---|---|
| Code | `hosted/` (`python -m hosted.server`) | `demo/` |
| Deploy config | `.deploy-app/` — `bash deploy.sh` | `.deploy/` — `bash deploy-demo.sh` |
| Server slug | `alpha-lab` (`/opt/sites/alpha-lab/`) | `alpha` |
| Data | live Yahoo + SEC, Flow Scanner refresh on | frozen snapshot |
| Access | owner email + password | email code, 7-day trial |
| Broker | absent (`lib/live/` deleted, no `ib_async`) | absent |

## Login

One email and one password, checked by `hosted/login.py`. The server only
holds a hash, in `/opt/sites/alpha-lab/.env`:

```
SITE_LOGIN_EMAIL=...
SITE_LOGIN_PASSWORD_HASH=scrypt:32768:8:1$...
```

The plain password lives only on the owner's PC, in
`~/.config/hetzner-site/owner-login.env`. The hetzner-site skill's
"Owner login" section has the one-line command that turns it into the two
lines above. Without both, the app refuses to start and the deploy rolls back.

Sessions last 14 days. Changing the password signs every browser out.
Five wrong tries from one IP lock the form for 15 minutes. `/logout` signs out.

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
