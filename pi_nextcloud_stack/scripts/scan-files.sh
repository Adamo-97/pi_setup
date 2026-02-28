#!/usr/bin/env bash
# ============================================================================
# scan-files.sh — Force Nextcloud to Index New AI Content
# ============================================================================
# When n8n pipelines write .mp4/.mp3 files to the ai-content directories,
# Nextcloud doesn't know about them until a file scan runs. This script:
#   1. Fixes permissions (www-data ownership)
#   2. Runs occ files:scan on the ai-content directory
#   3. Logs file counts per platform
#
# Cron (installed by setup.sh):
#   */15 * * * *  /path/to/scripts/scan-files.sh >> /var/log/nextcloud-scan.log 2>&1
#
# Manual:
#   ./scripts/scan-files.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source environment
if [[ -f "${PROJECT_DIR}/.env" ]]; then
    set -a; source "${PROJECT_DIR}/.env"; set +a
fi

NVME="${NVME_MOUNT:-/mnt/nvme}"
AI_DIR="${NVME}/ai-content"
ADMIN_USER="${NEXTCLOUD_ADMIN_USER:-admin}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# ── Pre-flight: Is the Nextcloud container running? ────────────────────────
if ! docker inspect --format='{{.State.Running}}' nextcloud 2>/dev/null | grep -q true; then
    echo "[${TIMESTAMP}] SKIP: Nextcloud container is not running"
    exit 0
fi

# ── Fix permissions on ai-content before scanning ──────────────────────────
if [[ -d "$AI_DIR" ]]; then
    sudo chown -R 33:33 "$AI_DIR" 2>/dev/null || true
    sudo find "$AI_DIR" -type d -exec chmod 2775 {} \; 2>/dev/null || true
    sudo find "$AI_DIR" -type f -exec chmod 664 {} \; 2>/dev/null || true
fi

# ── Count files per platform ──────────────────────────────────────────────
TOTAL=0
for platform in youtube tiktok instagram x; do
    if [[ -d "${AI_DIR}/${platform}" ]]; then
        count=$(find "${AI_DIR}/${platform}" -type f 2>/dev/null | wc -l)
        ((TOTAL += count)) || true
    fi
done

# ── Run Nextcloud file scan ───────────────────────────────────────────────
echo "[${TIMESTAMP}] Scanning ai-content/ (${TOTAL} files across 4 platforms)..."

docker exec -u www-data nextcloud php occ files:scan \
    --path="/${ADMIN_USER}/files/ai-content" \
    --shallow \
    2>&1 || {
    echo "[${TIMESTAMP}] ERROR: occ files:scan failed"
    exit 1
}

echo "[${TIMESTAMP}] Scan complete — ${TOTAL} files indexed"
