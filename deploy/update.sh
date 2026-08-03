#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/inkfall/project}"
SERVICE_NAME="${SERVICE_NAME:-inkfall.service}"

if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "Repository not found at $APP_DIR"
  exit 1
fi

git -C "$APP_DIR" fetch --all --tags
git -C "$APP_DIR" checkout main
git -C "$APP_DIR" pull --ff-only origin main

"$APP_DIR/.venv/bin/pip" install --upgrade -r "$APP_DIR/requirements.txt"
systemctl restart "$SERVICE_NAME"
