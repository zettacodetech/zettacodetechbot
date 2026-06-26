#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/inomjon/zettacode-sales-bot"
SERVICE_NAME="zettacode-bot.service"

cd "$APP_DIR"
git pull --ff-only
"$APP_DIR/.venv/bin/python" -m py_compile main.py
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
