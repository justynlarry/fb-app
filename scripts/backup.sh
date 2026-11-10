#!/bin/sh
# Nightly pg_dump into ./backups, keeping BACKUP_KEEP_DAYS days of dumps.
# Runs inside the "backup" container. Dumps at about 03:00 local time (TZ from .env).
set -eu

KEEP="${BACKUP_KEEP_DAYS:-14}"

while true; do
  # Sleep until the next 03:00
  now=$(date +%s)
  next=$(date -d "tomorrow 03:00" +%s 2>/dev/null || echo $((now + 86400)))
  if [ "$(date +%H)" -lt 3 ]; then
    next=$(date -d "today 03:00" +%s 2>/dev/null || echo "$next")
  fi
  sleep $((next - now))

  file="/backups/cfb-$(date +%Y-%m-%d).dump"
  if pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup ok: $file"
  else
    rm -f "$file.tmp"
    echo "backup FAILED" >&2
  fi

  find /backups -name 'cfb-*.dump' -mtime +"$KEEP" -delete
done
