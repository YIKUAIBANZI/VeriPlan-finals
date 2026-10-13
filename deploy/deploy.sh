#!/bin/sh
# Deploy VeriPlan to the shared VPS. Touches only /opt/veriplan, veriplan.service,
# /etc/nginx/sites-enabled/veriplan.conf and /etc/nginx/veriplan.htpasswd.
# Usage: SSHPASS=... HTPASS=... ./deploy/deploy.sh   (run from repo root, proxy off)
set -eu
HOST=root@8.136.210.14
SSH="sshpass -e ssh -o StrictHostKeyChecking=accept-new"
KEYS="$HOME/.config/veriplan/live-keys.env"

ENVFILE=$(mktemp); trap 'rm -f "$ENVFILE"' EXIT
{
  grep -E '^(DEEPSEEK_API_KEY|TAVILY_API_KEY)=' "$KEYS"
  echo "APP_MODE=live"
  echo "ENABLE_LIVE_WORKFLOW=true"
  echo "DATABASE_URL=sqlite:////opt/veriplan/data/veriplan.db"
  echo "DEEPSEEK_TIMEOUT_SECONDS=60"
  echo "SKEPTIC_REVIEW_PASS=true"
} > "$ENVFILE"

(cd frontend && npm run build >/dev/null)
$SSH $HOST 'id veriplan >/dev/null 2>&1 || useradd --system --no-create-home veriplan; mkdir -p /opt/veriplan/data'
rsync -az --delete --exclude=.git --exclude=.venv --exclude=node_modules --exclude='*.db' \
  --exclude=docs --exclude=artifacts -e "$SSH" ./ $HOST:/opt/veriplan/
rsync -az -e "$SSH" "$ENVFILE" $HOST:/opt/veriplan/.env
$SSH $HOST "set -e
  cd /opt/veriplan/backend
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\$HOME/.local/bin:\$PATH
  [ -x .venv/bin/python ] || uv venv -q -p 3.12 .venv
  uv pip install -q -p .venv/bin/python -e .
  chmod 600 /opt/veriplan/.env && chown -R veriplan /opt/veriplan/data /opt/veriplan/.env
  printf 'veriplan:%s\n' \"\$(openssl passwd -apr1 '$HTPASS')\" > /etc/nginx/veriplan.htpasswd
  cp /opt/veriplan/deploy/veriplan.service /etc/systemd/system/veriplan.service
  cp /opt/veriplan/deploy/veriplan.nginx.conf /etc/nginx/sites-enabled/veriplan.conf
  systemctl daemon-reload && systemctl enable --now veriplan && systemctl restart veriplan
  nginx -t && systemctl reload nginx
  sleep 2; curl -s http://127.0.0.1:9195/api/health"
echo
echo "Next (once DNS resolves): certbot --nginx -d veriplan.yikuaibanz.cn -n --agree-tos --redirect"
