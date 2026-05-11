#!/usr/bin/env bash
# Run on the Hetzner host (not Windows). Called by enable_sfa_tls.ps1 via ssh, or:
#   bash scripts/enable_sfa_tls.sh
set -euo pipefail

DOMAIN="${SFA_TLS_DOMAIN:-sfa.noeinsolutions.com}"
UPSTREAM_HOST="${SFA_UPSTREAM_HOST:-172.18.0.1}"
UPSTREAM_PORT="${SFA_UPSTREAM_PORT:-8060}"
CONF="/opt/bep-generator/nginx/conf.d/default.conf"
NGINX_CONTAINER="${NGINX_CONTAINER:-bep-generator-nginx-1}"

if [[ ! -f "$CONF" ]]; then
  echo "ERR: missing $CONF" >&2
  exit 1
fi

restart_nginx() {
  docker exec "$NGINX_CONTAINER" nginx -t
  docker restart "$NGINX_CONTAINER" >/dev/null
  sleep 2
}

# 1) Ensure HTTP vhost allows ACME webroot (required before first cert)
python3 <<PY
from pathlib import Path
conf = Path("${CONF}")
text = conf.read_text()
start = "# BEGIN SFA DASHBOARD VHOST"
end = "# END SFA DASHBOARD VHOST"
if start not in text or end not in text:
    raise SystemExit("ERR: SFA vhost markers not found in nginx config")

before, rest = text.split(start, 1)
block, after = rest.split(end, 1)
if "location /.well-known/acme-challenge/" not in block:
    old = """  server_name ${DOMAIN};

  location / {"""
    new = """  server_name ${DOMAIN};

  location /.well-known/acme-challenge/ {
    root /var/www/certbot;
  }

  location / {"""
    if old not in block:
        raise SystemExit("ERR: expected SFA HTTP block shape not found; edit $CONF manually")
    block = block.replace(old, new, 1)
text = before + start + block + end + after
conf.write_text(text)
PY

restart_nginx

# 2) Issue certificate
certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --agree-tos \
  --register-unsafely-without-email \
  --non-interactive

# 3) Replace HTTP SFA block with ACME + redirect; add or replace HTTPS reverse-proxy block
python3 <<PY
import re
from pathlib import Path

conf = Path("${CONF}")
domain = "${DOMAIN}"
upstream = "${UPSTREAM_HOST}:${UPSTREAM_PORT}"
text = conf.read_text()

http_block = f"""server {{
  listen 80;
  server_name {domain};

  location /.well-known/acme-challenge/ {{
    root /var/www/certbot;
  }}

  location / {{
    return 301 https://$host$request_uri;
  }}
}}"""

http_section = f"# BEGIN SFA DASHBOARD VHOST\n{http_block}\n# END SFA DASHBOARD VHOST"
text, n = re.subn(
    r"# BEGIN SFA DASHBOARD VHOST\n.*?\n# END SFA DASHBOARD VHOST",
    http_section,
    text,
    count=1,
    flags=re.DOTALL,
)
if n != 1:
    raise SystemExit("ERR: could not replace SFA HTTP vhost section")

tls_block = f"""# BEGIN SFA DASHBOARD TLS VHOST
server {{
  listen 443 ssl;
  http2 on;
  server_name {domain};

  ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;

  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers on;

  location / {{
    proxy_pass http://{upstream};
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
  }}
}}
# END SFA DASHBOARD TLS VHOST"""

if "# BEGIN SFA DASHBOARD TLS VHOST" in text:
    text, m = re.subn(
        r"# BEGIN SFA DASHBOARD TLS VHOST\n.*?\n# END SFA DASHBOARD TLS VHOST",
        tls_block,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if m != 1:
        raise SystemExit("ERR: could not replace SFA TLS vhost section")
else:
    text = text.rstrip() + "\n\n" + tls_block + "\n"

conf.write_text(text)
PY

restart_nginx
echo "ok  TLS enabled for https://${DOMAIN}/"
