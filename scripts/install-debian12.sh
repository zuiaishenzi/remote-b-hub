#!/usr/bin/env bash
set -Eeuo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo 'Run as root: bash scripts/install-debian12.sh' >&2
  exit 1
fi
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip curl openssl
if ! id remotebhub >/dev/null 2>&1; then
  useradd --system --home /opt/remote-b-hub --shell /usr/sbin/nologin remotebhub
fi
install -d -o remotebhub -g remotebhub -m 0750 /opt/remote-b-hub
install -d -o root -g root -m 0700 /etc/remote-b-hub
install -o remotebhub -g remotebhub -m 0644 "$ROOT_DIR/linux-server/server.py" /opt/remote-b-hub/server.py
install -o remotebhub -g remotebhub -m 0644 "$ROOT_DIR/linux-server/requirements.txt" /opt/remote-b-hub/requirements.txt
if [ ! -e /etc/remote-b-hub/hub.env ]; then
  umask 077
  A_TOKEN="$(openssl rand -hex 32)"
  B_TOKEN="$(openssl rand -hex 32)"
  printf 'HUB_A_TOKEN=%s\nHUB_B_TOKEN=%s\nHUB_DB=/opt/remote-b-hub/jobs.sqlite3\n' "$A_TOKEN" "$B_TOKEN" > /etc/remote-b-hub/hub.env
  unset A_TOKEN B_TOKEN
  echo 'Generated new credentials at /etc/remote-b-hub/hub.env'
else
  echo 'Keeping existing credentials at /etc/remote-b-hub/hub.env'
fi
chmod 0600 /etc/remote-b-hub/hub.env
chown root:root /etc/remote-b-hub/hub.env
if [ ! -x /opt/remote-b-hub/.venv/bin/python ]; then
  runuser -u remotebhub -- python3 -m venv /opt/remote-b-hub/.venv
fi
runuser -u remotebhub -- /opt/remote-b-hub/.venv/bin/python -m pip install -r /opt/remote-b-hub/requirements.txt
install -o root -g root -m 0644 "$ROOT_DIR/linux-server/remote-b-hub.service" /etc/systemd/system/remote-b-hub.service
systemctl daemon-reload
systemctl enable --now remote-b-hub
systemctl restart remote-b-hub
sleep 1
systemctl --no-pager --full status remote-b-hub || true
curl --fail --show-error --silent http://127.0.0.1:18765/health
echo
echo 'Done. Local hub port: 127.0.0.1:18765'
echo 'Configure your HTTPS tunnel separately; never publish hub.env.'
