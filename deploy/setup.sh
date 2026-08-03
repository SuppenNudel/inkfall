#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/inkfall/project}"
REPO_URL="${REPO_URL:-https://github.com/SuppenNudel/inkfall.git}"
APP_USER="${APP_USER:-inkfall}"
SERVICE_NAME="${SERVICE_NAME:-inkfall.service}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Please run this script as root with sudo."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv python3-pip python3-git nginx certbot python3-certbot-nginx git

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

install -d -o "$APP_USER" -g www-data -m 755 "$APP_DIR"

if [[ ! -d "$APP_DIR/.git" ]]; then
  sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
fi

# Ensure the repository is owned by the application user so git does not complain
# about dubious ownership when scripts run later under the service account.
chown -R "$APP_USER:www-data" "$APP_DIR"
chmod -R u+rwX,g+rX,o-rwx "$APP_DIR"

sudo -u "$APP_USER" git -C "$APP_DIR" config --global --add safe.directory "$APP_DIR"
sudo -u "$APP_USER" git -C "$APP_DIR" fetch --all --tags
sudo -u "$APP_USER" git -C "$APP_DIR" checkout main
sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only origin main

sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ -f "$APP_DIR/deploy/inkfall.service" ]]; then
  cp "$APP_DIR/deploy/inkfall.service" "/etc/systemd/system/$SERVICE_NAME"
else
  echo "Missing service unit template: $APP_DIR/deploy/inkfall.service" >&2
  exit 1
fi
cp "$APP_DIR/deploy/inkfall-webhook.service" /etc/systemd/system/
cp "$APP_DIR/deploy/inkfall.de.nginx.conf" /etc/nginx/sites-available/inkfall.de
cp "$APP_DIR/deploy/inkfall-webhook.nginx.conf" /etc/nginx/snippets/inkfall-webhook.conf
ln -sf /etc/nginx/sites-available/inkfall.de /etc/nginx/sites-enabled/inkfall.de
rm -f /etc/nginx/sites-enabled/default

if ! grep -q "include /etc/nginx/snippets/inkfall-webhook.conf;" /etc/nginx/sites-available/inkfall.de; then
  printf '\ninclude /etc/nginx/snippets/inkfall-webhook.conf;\n' >> /etc/nginx/sites-available/inkfall.de
fi

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl enable --now inkfall-webhook.service
nginx -t
systemctl reload nginx

cat <<EOF

Setup complete.

Important:
  Edit the webhook secret before using it in production:
  sudo systemctl edit inkfall-webhook.service

Useful commands:
  sudo systemctl status $SERVICE_NAME
  sudo systemctl status inkfall-webhook.service
  sudo journalctl -u $SERVICE_NAME -f
  sudo journalctl -u inkfall-webhook.service -f

Your app is expected to be reachable at:
  https://inkfall.de

GitHub webhook URL:
  https://inkfall.de/github-webhook/
EOF
