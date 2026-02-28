#!/usr/bin/env bash
# =============================================================
# pi_hole_stack — Gravity (Blocklist) Update Script
# =============================================================
# Updates Pi-hole's gravity database (blocklists).
# Designed to run via cron: 0 3 * * 0 /path/to/update-gravity.sh
#
# The setup.sh script installs this as a weekly cron job
# (Sunday 3:00 AM). You can also run it manually:
#   ./update-gravity.sh
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

log() { echo "[$TIMESTAMP] $1"; }

# -----------------------------------------------------------
# 1. Update gravity (blocklists)
# -----------------------------------------------------------
log "Starting Pi-hole gravity update..."

if ! docker ps --filter "name=pihole" --filter "status=running" -q | grep -q .; then
    log "ERROR: Pi-hole container is not running. Aborting."
    exit 1
fi

docker exec pihole pihole -g

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    log "Gravity update completed successfully."
else
    log "ERROR: Gravity update failed with exit code $EXIT_CODE."
    exit $EXIT_CODE
fi

# -----------------------------------------------------------
# 2. Update Pi-hole container image (optional, conservative)
# -----------------------------------------------------------
# Uncomment the following lines to also pull the latest Pi-hole
# image during the weekly update:
#
# log "Pulling latest Pi-hole image..."
# cd "$SCRIPT_DIR"
# docker compose pull pihole
# docker compose up -d pihole
# log "Pi-hole container updated."

# -----------------------------------------------------------
# 3. Log summary
# -----------------------------------------------------------
BLOCKED=$(docker exec pihole pihole -c -e 2>/dev/null | grep -oP 'Blocked: \K[\d,]+' || echo "N/A")
TOTAL=$(docker exec pihole pihole -c -e 2>/dev/null | grep -oP 'Total: \K[\d,]+' || echo "N/A")

log "Domains on blocklist: $(docker exec pihole pihole -g -l 2>/dev/null | tail -1 || echo 'check manually')"
log "Gravity update done."
