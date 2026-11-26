#!/bin/sh
# Runs on fb-line (the VM, backed up by Proxmox Backup Server), NOT on devGray.
# Copies devGray's nightly pg_dump files here, so they are covered by PBS.
# Pull, not push: devGray holds no login for this VM, so a broken or compromised
# devGray can't delete these copies.
#
# Cron (fb-user on fb-line), 03:30 = 30 min after devGray's 03:00 dump:
#   30 3 * * * /home/fb-user/fb-app/scripts/pull-backups.sh >> /home/fb-user/devgray-backups.log 2>&1
set -eu

SRC="dev-user@192.168.0.223:fb-app/backups/"
DEST="$HOME/devgray-backups"
KEEP_DAYS=90          # devGray itself keeps BACKUP_KEEP_DAYS (14); keep longer here

mkdir -p "$DEST"

# No --delete: a dump that disappears on devGray stays here until KEEP_DAYS.
# Only finished dumps (backup.sh writes *.tmp first, then renames).
rsync -a --exclude '*.tmp' -e "ssh -o BatchMode=yes -o ConnectTimeout=20" "$SRC" "$DEST/"

find "$DEST" -name 'cfb-*.dump' -mtime +"$KEEP_DAYS" -delete

newest=$(ls -t "$DEST"/cfb-*.dump 2>/dev/null | head -1)
echo "$(date '+%F %T') ok, newest: ${newest:-none}"

# Warn if the newest dump is more than 36 h old (devGray's backup container stopped?)
if [ -n "$newest" ] && [ -n "$(find "$newest" -mmin +2160)" ]; then
  echo "$(date '+%F %T') WARNING: newest dump is older than 36 h" >&2
fi
