#!/usr/bin/env bash
# Run on the Linux host as root (e.g. via deploy.ps1). Fixes OpenClaw / non-root
# access to the venv, Optuna state, project tree, and installs /usr/local/bin/sfa.
set -euo pipefail

APP="${SFA_APP:-/opt/searchforalpha}"

if [[ ! -d "$APP" ]]; then
  echo "error: directory not found: $APP" >&2
  exit 1
fi

# Traverse /opt and app root (often 750 root:root blocks other users' cd)
chmod o+rx /opt 2>/dev/null || true
chmod o+rx "$APP" 2>/dev/null || true

chmod -R 755 "$APP/lib" "$APP/config"

if [[ -d "$APP/.venv" ]]; then
  chmod -R a+rX "$APP/.venv"
fi

mkdir -p "$APP/state"

if id openclaw &>/dev/null; then
  chown -R openclaw:openclaw "$APP/state" || true
  chmod -R u+rwX "$APP/state"
  setfacl -m "u:openclaw:rw" "$APP/config/strategy_config.yaml"
  setfacl -m "u:openclaw:r--" "$APP/config/agent.yaml"
else
  echo "warn: user openclaw not found — skipped chown state and setfacl" >&2
fi

TMP="$(mktemp)"
{
  echo '#!/bin/sh'
  printf 'exec %s/.venv/bin/python -m lib.cli.app "$@"\n' "$APP"
} >"$TMP"
if command -v install &>/dev/null; then
  install -m 755 -o root -g root "$TMP" /usr/local/bin/sfa
else
  cp "$TMP" /usr/local/bin/sfa
  chmod 755 /usr/local/bin/sfa
  chown root:root /usr/local/bin/sfa 2>/dev/null || true
fi
rm -f "$TMP"

echo "ok: openclaw/sfa server permissions applied for $APP"
