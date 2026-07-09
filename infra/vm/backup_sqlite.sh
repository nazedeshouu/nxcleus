#!/usr/bin/env bash
# Nightly SQLite backup for the Nxcleus control plane (spec 05 §6).
#
# Runs on the VM HOST (installed as a root cron by infra/vm/README "Backups"). Takes a
# CONSISTENT snapshot with `sqlite3 .backup` (safe while uvicorn holds the DB open / WAL),
# gzips it, and keeps the newest RETENTION copies off the docker volume (on the host disk,
# so a volume loss still leaves recoverable backups). Cheap insurance before demo days.
#
# Usage:   backup_sqlite.sh            # normal nightly run
#          RETENTION=14 backup_sqlite.sh
set -euo pipefail

VOLUME="${PLATFORM_VOLUME:-vm_platform-data}"
DEST="${BACKUP_DIR:-/root/nxcleus-backups}"
RETENTION="${RETENTION:-7}"
LOG="${BACKUP_LOG:-/var/log/nxcleus-backup.log}"

log() { echo "$(date -Is) $*" | tee -a "$LOG"; }

MP="$(docker volume inspect "$VOLUME" -f '{{.Mountpoint}}' 2>/dev/null || true)"
DB="${SQLITE_DB:-${MP}/platform.db}"

if [ -z "$MP" ] || [ ! -f "$DB" ]; then
  log "WARN no db at '${DB}' (volume=${VOLUME}) — nothing to back up"
  exit 0
fi

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${DEST}/platform-${STAMP}.db"

sqlite3 "$DB" ".backup '${OUT}'"
gzip -f "$OUT"

# retention: delete all but the newest $RETENTION gzipped backups.
# ls -1t (mtime sort) is intentional and safe here — filenames are controlled timestamps.
# shellcheck disable=SC2012
ls -1t "${DEST}"/platform-*.db.gz 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -r rm -f

log "backup ok -> ${OUT}.gz ($(du -h "${OUT}.gz" | cut -f1)); kept newest ${RETENTION}"
