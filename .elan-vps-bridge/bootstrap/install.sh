#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/elan-web-vps-bridge
STATE_DIR=/var/lib/elan-web-vps-bridge
UNIT=/etc/systemd/system/elan-web-vps-bridge.service
RUN_USER=${ELAN_BRIDGE_USER:-ubuntu}
BASE_RAW=https://raw.githubusercontent.com/romainbresil/public_html/elan-vps-bridge-control-v1/.elan-vps-bridge/bootstrap

id "$RUN_USER" >/dev/null
command -v python3 >/dev/null
command -v openssl >/dev/null
command -v curl >/dev/null

install -d -o "$RUN_USER" -g "$RUN_USER" -m 0750 "$APP_DIR" "$STATE_DIR" "$STATE_DIR/claims" "$STATE_DIR/results" "$STATE_DIR/incoming"
curl -fsSL "$BASE_RAW/bridge_worker.py" -o "$APP_DIR/bridge_worker.py"
curl -fsSL "$BASE_RAW/issue_inbox.py" -o "$APP_DIR/issue_inbox.py"
chown "$RUN_USER:$RUN_USER" "$APP_DIR/bridge_worker.py" "$APP_DIR/issue_inbox.py"
chmod 0755 "$APP_DIR/bridge_worker.py" "$APP_DIR/issue_inbox.py"

if [[ ! -s "$STATE_DIR/private.key" || ! -s "$STATE_DIR/public.crt" ]]; then
  sudo -u "$RUN_USER" openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 3650 \
    -subj '/CN=elan-web-vps-bridge' \
    -keyout "$STATE_DIR/private.key" -out "$STATE_DIR/public.crt" >/dev/null 2>&1
  chmod 0600 "$STATE_DIR/private.key"
  chmod 0644 "$STATE_DIR/public.crt"
fi

cat > "$UNIT" <<EOF
[Unit]
Description=Elan Naturel ChatGPT Web VPS bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
Environment=PYTHONUNBUFFERED=1
Environment=ELAN_BRIDGE_STATE_ROOT=$STATE_DIR
Environment=ELAN_BRIDGE_CONTROL_REPO=romainbresil/public_html
Environment=ELAN_BRIDGE_ISSUE_AUTHOR=romainbresil
Environment=ELAN_BRIDGE_POLL_SECONDS=60
Environment=ELAN_BRIDGE_RESULT_HOST=127.0.0.1
Environment=ELAN_BRIDGE_RESULT_PORT=8789
Environment=ELAN_BRIDGE_RETURN_ENDPOINT=https://romainbecquart.com/__elan-vps-bridge-return.html
ExecStart=/usr/bin/python3 $APP_DIR/issue_inbox.py
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$STATE_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable elan-web-vps-bridge.service >/dev/null
systemctl restart elan-web-vps-bridge.service
systemctl is-active --quiet elan-web-vps-bridge.service
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8789/healthz >/dev/null 2>&1 || curl -fsS http://10.0.1.1:8789/healthz >/dev/null 2>&1; then
    exit 0
  fi
  sleep 0.25
done
exit 1
