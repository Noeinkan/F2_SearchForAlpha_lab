#!/usr/bin/env bash
# deploy.sh — publish the research workspace (slug alpha-lab) at
# https://alpha.noeinsolutions.com, behind the owner login.
#
# Not the demo: deploy-demo.sh ships .deploy/ (alpha.demos.noeinsolutions.com).
# This one ships .deploy-app/, i.e. hosted/server.py.
#
#   bash deploy.sh              deploy the ref in .deploy-app/site.json
#   bash deploy.sh --dry-run    print what would happen, change nothing
#   bash deploy.sh --rollback   restore the last good commit
#
# All arguments go straight to the hetzner-site skill's site-deploy.sh.

set -euo pipefail

for candidate in \
    "${HETZNER_SITE_SKILL:-}" \
    "$HOME/.claude/skills/hetzner-site" \
    "/c/Personal_utilities/hetzner-site" \
    "/mnt/c/Personal_utilities/hetzner-site"; do
    if [ -n "$candidate" ] && [ -x "$candidate/bin/site-deploy.sh" ]; then
        SKILL_DIR="$candidate"
        break
    fi
done

if [ -z "${SKILL_DIR:-}" ]; then
    echo "deploy.sh: cannot find the hetzner-site skill." >&2
    echo "  Set HETZNER_SITE_SKILL=/path/to/hetzner-site and retry." >&2
    exit 1
fi

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec bash "$SKILL_DIR/bin/site-deploy.sh" --config "$PWD/.deploy-app" "$@"
