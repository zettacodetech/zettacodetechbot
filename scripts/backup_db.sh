#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/inomjon/zettacode-sales-bot"
BACKUP_DIR="$APP_DIR/backups"
DB_FILE="$APP_DIR/orders.db"

mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_FILE" ]]; then
  echo "Database topilmadi: $DB_FILE" >&2
  exit 1
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
cp "$DB_FILE" "$BACKUP_DIR/orders_backup_$timestamp.db"
echo "Backup yaratildi: $BACKUP_DIR/orders_backup_$timestamp.db"
